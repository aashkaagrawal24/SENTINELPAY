import json
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.auth.dependencies import AuthenticatedUser, get_current_user
from app.core.config import Settings, get_settings
from app.db.session import get_db_session
from app.schemas.buyer import ParsedIntent
from app.schemas.phase9 import ProvenanceCreate
from app.services.agents import BuyerAgent, MerchantAgent
from app.services.audit_ledger import AuditLedgerService
from app.services.mandate_service import MandateService
from app.services.model_gateway import ModelGateway
from app.services.provenance_service import ProvenanceService

router = APIRouter(prefix="/api")


def get_intent_model_gateway(
    settings: Settings = Depends(get_settings),
) -> ModelGateway:
    return ModelGateway.from_settings(settings, "INTENT_PARSING")


async def compile_intent(
    raw_text: str, gateway: ModelGateway
) -> tuple[ParsedIntent | None, str | None, dict | None]:
    prompt = (
        "Interpret this buyer request as a structured commerce intent. "
        "CRITICAL RULE — Budget must ALWAYS be in MINOR UNITS (paise). "
        "Multiply the user's stated INR amount by 100 to get minor units. "
        "Examples: '400000 INR' → max_budget_minor=40000000 | '50000 INR' → max_budget_minor=5000000 | '1 lakh' → max_budget_minor=10000000 | '4 lakh' → max_budget_minor=40000000. "
        "Never store the raw rupee amount as minor units — always multiply by 100. "
        "Understand natural language and multilingual/Hinglish inputs like 'kam de isse' (meaning negotiation allowed). "
        "If budget is not mentioned explicitly, try to infer it from product type or leave max_budget_minor as null. "
        "CRITICAL RULE — allowed_conditions MUST ONLY contain valid physical product conditions like 'NEW', 'USED', 'REFURBISHED', 'USED_GOOD'. NEVER put pricing logic or budget limits in allowed_conditions. "
        "Do NOT increase budgets, permissions, quantities, or purchase authority. "
        f"Buyer request: {raw_text}"
    )
    try:
        proposal, trace = await gateway.parse(prompt, ParsedIntent)
    except RuntimeError as exc:
        raise HTTPException(503, "Intent model providers unavailable; request denied") from exc

    trace_dict = {
        "provider": trace.provider,
        "model": trace.model,
        "task": trace.task,
        "latency_ms": trace.latency_ms,
    }

    if not proposal.product_query or proposal.product_query.strip() == "":
        return None, "What specific product are you looking to buy?", trace_dict

    if proposal.max_budget_minor is None:
        return None, "What is your maximum budget in INR?", trace_dict

    # Safety guard: if LLM returned a suspiciously small budget (looks like it forgot ×100),
    # detect and correct. Heuristic: raw_text contains a number ≥1000 but budget < that × 2.
    import re as _re
    _numbers_in_text = [int(n.replace(",", "")) for n in _re.findall(r"[\d,]+", raw_text) if int(n.replace(",", "")) >= 1000]
    if _numbers_in_text and proposal.max_budget_minor is not None:
        _largest_raw = max(_numbers_in_text)
        if proposal.max_budget_minor <= _largest_raw * 2:
            proposal = proposal.model_copy(update={"max_budget_minor": proposal.max_budget_minor * 100})

    if not proposal.allowed_conditions:
        return None, "Are you looking for NEW or USED items? (Or both?)", trace_dict

    # ALWAYS enable all autonomous AI flags — the system is designed to act on the buyer's
    # behalf. No magic phrase needed; the mandate confirmation step is the user's consent gate.
    proposal = proposal.model_copy(update={
        "negotiation_allowed": True,
        "upsell_allowed": True,
        "cross_sell_allowed": True,
        "campaign_offer_allowed": True,
    })

    return proposal, None, trace_dict



def owned_row(db: Session, table: str, entity_id: UUID, user_id: UUID) -> dict:
    if table not in {"intents", "mandates", "conversation_threads"}:
        raise ValueError("Unsupported ownership table")
    row = (
        db.execute(
            text(f"select * from {table} where id=:id and user_id=:user"),
            {"id": entity_id, "user": user_id},
        )
        .mappings()
        .one_or_none()
    )
    if not row:
        raise HTTPException(404, "Resource not found")
    return dict(row)


@router.post("/conversations")
def create_conversation(
    user: AuthenticatedUser = Depends(get_current_user), db: Session = Depends(get_db_session)
):
    session = (
        db.execute(
            text("insert into agent_sessions(user_id,status) values(:u,'ACTIVE') returning id"),
            {"u": user.id},
        )
        .mappings()
        .one()
    )
    thread = (
        db.execute(
            text(
                "insert into conversation_threads(user_id,agent_session_id) values(:u,:s) returning id,created_at"
            ),
            {"u": user.id, "s": session["id"]},
        )
        .mappings()
        .one()
    )
    db.commit()
    return {**dict(thread), "agent_session_id": session["id"]}


@router.get("/conversations/{thread_id}")
def get_conversation(
    thread_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    thread = owned_row(db, "conversation_threads", thread_id, user.id)
    messages = [
        dict(row)
        for row in db.execute(
            text(
                "select id,role,content,payload,source_category,created_at from conversation_messages where thread_id=:t order by created_at"
            ),
            {"t": thread_id},
        ).mappings()
    ]
    return {**thread, "messages": messages}


@router.post("/intents")
async def create_intent(
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    gateway: ModelGateway = Depends(get_intent_model_gateway),
):
    raw_text = str(body.get("raw_text", "")).strip()
    if not raw_text:
        raise HTTPException(422, "raw_text required")
    parsed, clarification, model_trace = await compile_intent(raw_text, gateway)
    if clarification:
        return {
            "status": "REQUIRES_CLARIFICATION",
            "clarification": clarification,
            "raw_text": raw_text,
        }
    row = (
        db.execute(
            text(
                "insert into intents(user_id,raw_text,parsed_payload,parser_provider,parser_model,parser_version,schema_version) values(:u,:raw,cast(:payload as jsonb),:provider,:model,:version,'1.0') returning id,created_at"
            ),
            {
                "u": user.id,
                "raw": raw_text,
                "payload": parsed.model_dump_json(),
                "provider": model_trace["provider"],
                "model": model_trace["model"],
                "version": model_trace["task"],
            },
        )
        .mappings()
        .one()
    )
    db.commit()
    AuditLedgerService().append(
        db,
        scope=f"INTENT:{row['id']}",
        event_type="INTENT_RECEIVED",
        actor="BUYER_AGENT",
        payload={"intent_id": str(row["id"]), "parser_provider": model_trace["provider"]},
        user_id=user.id,
    )
    db.commit()
    return {
        **dict(row),
        "status": "PARSED",
        "parsed_intent": parsed,
        "provenance": {
            "raw_text": "USER_INPUT",
            "parsed_intent": "MODEL_DERIVED",
            "authority_constraints": "SYSTEM_DERIVED",
            "confirmation": "REQUIRED",
        },
        "model_call": model_trace,
    }


@router.get("/intents/{intent_id}")
def get_intent(
    intent_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    return owned_row(db, "intents", intent_id, user.id)


@router.post("/mandates")
def create_mandate(
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    if body.get("confirmed") is not True:
        raise HTTPException(409, "User confirmation required before mandate activation")
    intent = owned_row(db, "intents", UUID(str(body["intent_id"])), user.id)
    payload = (
        intent["parsed_payload"]
        if isinstance(intent["parsed_payload"], dict)
        else json.loads(intent["parsed_payload"])
    )
    parsed = ParsedIntent.model_validate(payload)
    authority = MandateService().authority(parsed)
    nonce = uuid4()
    row = (
        db.execute(
            text(
                """insert into mandates(user_id,intent_id,product_scope,max_total_amount_minor,currency,max_quantity,allowed_conditions,preferred_brands,excluded_brands,negotiation_allowed,upsell_allowed,cross_sell_allowed,campaign_offer_allowed,auto_purchase_allowed,expires_at,nonce,integrity_hash,status) values(:u,:intent,cast(:scope as jsonb),:budget,:currency,:quantity,cast(:conditions as jsonb),cast(:preferred as jsonb),cast(:excluded as jsonb),:negotiation,:upsell,:cross_sell,:campaign,false,:expires,:nonce,:hash,'ACTIVE') returning *"""
            ),
            {
                "u": user.id,
                "intent": intent["id"],
                "scope": json.dumps(authority["product_scope"]),
                "budget": authority["max_total_amount_minor"],
                "currency": authority["currency"],
                "quantity": authority["max_quantity"],
                "conditions": json.dumps(authority["allowed_conditions"]),
                "preferred": json.dumps(authority["preferred_brands"]),
                "excluded": json.dumps(authority["excluded_brands"]),
                "negotiation": authority["negotiation_allowed"],
                "upsell": authority["upsell_allowed"],
                "cross_sell": authority["cross_sell_allowed"],
                "campaign": authority["campaign_offer_allowed"],
                "expires": authority["expires_at"],
                "nonce": nonce,
                "hash": MandateService().hash(authority),
            },
        )
        .mappings()
        .one()
    )
    db.commit()
    budget_provenance = ProvenanceService().create(
        db,
        ProvenanceCreate(
            entity_type="MANDATE",
            entity_id=row["id"],
            field_name="max_total_amount_minor",
            value_snapshot=row["max_total_amount_minor"],
            unit=f"{row['currency']}_MINOR",
            value_type="REAL_DATA",
            trust_class="USER_SIGNED",
            method="Visible confirmation before mandate activation",
            source="BUYER_CONFIRMATION",
            financial_authority=True,
            user_id=user.id,
        ),
    )
    AuditLedgerService().append(
        db,
        scope=f"MANDATE:{row['id']}",
        event_type="MANDATE_CREATED",
        actor="BUYER",
        payload={"mandate_id": str(row["id"]), "status": "ACTIVE"},
        user_id=user.id,
        provenance_ids=[str(budget_provenance["id"])],
    )
    db.commit()
    return MandateService.safe_summary(dict(row))


@router.get("/mandates/{mandate_id}")
def get_mandate(
    mandate_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    return MandateService.safe_summary(owned_row(db, "mandates", mandate_id, user.id))


@router.post("/mandates/{mandate_id}/revoke")
def revoke_mandate(
    mandate_id: UUID,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
):
    result = db.execute(
        text(
            "update mandates set status='REVOKED' where id=:id and user_id=:user and status='ACTIVE'"
        ),
        {"id": mandate_id, "user": user.id},
    )
    if not result.rowcount:
        raise HTTPException(409, "Mandate is unavailable or no longer active")
    db.commit()
    return {"id": mandate_id, "status": "REVOKED"}


@router.post("/conversations/{thread_id}/messages")
async def add_message(
    thread_id: UUID,
    body: dict,
    user: AuthenticatedUser = Depends(get_current_user),
    db: Session = Depends(get_db_session),
    gateway: ModelGateway = Depends(get_intent_model_gateway),
):
    owned_row(db, "conversation_threads", thread_id, user.id)
    raw = str(body.get("content", "")).strip()

    # Fetch conversation history so the LLM has full context for follow-up replies
    # (e.g. when user says "new" or "400000" as an answer to a clarification question)
    prior_messages = db.execute(
        text(
            "select role, content, payload from conversation_messages "
            "where thread_id=:t order by created_at desc limit 10"
        ),
        {"t": thread_id},
    ).mappings().all()

    # Build history string: oldest first, most recent last.
    # For ASSISTANT messages the `content` column stores the status enum
    # ("REQUIRES_CLARIFICATION", …), so we read the actual human-readable
    # question/message from the `payload` JSON instead.
    history_lines = []
    resolved_intent: dict = {}  # carry forward already-answered fields
    for msg in reversed(prior_messages):
        role = msg["role"]
        content = (msg["content"] or "").strip()
        raw_payload = msg["payload"]
        payload: dict = {}
        if raw_payload:
            try:
                payload = json.loads(raw_payload) if isinstance(raw_payload, str) else raw_payload
            except Exception:  # noqa: BLE001
                payload = {}

        if role == "USER":
            if content:
                history_lines.append(f"Buyer: {content}")
        else:
            # Prefer the actual clarification question text from payload
            assistant_text = payload.get("message") or ""
            if not assistant_text and content not in ("REQUIRES_CLARIFICATION", "REQUIRES_MANDATE_CONFIRMATION"):
                assistant_text = content
            if assistant_text:
                history_lines.append(f"Assistant: {assistant_text}")

            # If a previous turn already produced a full parsed intent, carry those
            # fields forward so we don't re-ask for things the user already answered.
            if payload.get("status") == "REQUIRES_MANDATE_CONFIRMATION":
                pi = payload.get("parsed_intent") or {}
                if pi.get("product_query"):
                    resolved_intent.setdefault("product_query", pi["product_query"])
                if pi.get("max_budget_minor") is not None:
                    resolved_intent.setdefault("max_budget_minor", pi["max_budget_minor"])
                if pi.get("allowed_conditions"):
                    resolved_intent.setdefault("allowed_conditions", pi["allowed_conditions"])

    # Combine history + current message into a single context string for the LLM.
    # If we have previously resolved fields, prepend them so the LLM treats them
    # as already-known facts and doesn't ask again.
    resolved_prefix = ""
    if resolved_intent:
        parts = []
        if resolved_intent.get("product_query"):
            parts.append(f"product: {resolved_intent['product_query']}")
        if resolved_intent.get("max_budget_minor") is not None:
            parts.append(f"budget: {resolved_intent['max_budget_minor']} paise")
        if resolved_intent.get("allowed_conditions"):
            parts.append(f"condition: {', '.join(resolved_intent['allowed_conditions'])}")
        resolved_prefix = "[Already confirmed by buyer — do NOT ask again: " + "; ".join(parts) + "]\n"

    if history_lines:
        context_text = resolved_prefix + "\n".join(history_lines) + f"\nBuyer: {raw}"
    else:
        context_text = resolved_prefix + raw

    db.execute(
        text(
            "insert into conversation_messages(thread_id,role,content,source_category) values(:t,'USER',:content,'USER_INPUT')"
        ),
        {"t": thread_id, "content": raw},
    )
    parsed, clarification, model_trace = await compile_intent(context_text, gateway)

    if clarification:
        answer = {
            "status": "REQUIRES_CLARIFICATION",
            "message": clarification,
            "provenance": "SYSTEM_DERIVED",
        }
    else:
        merchant_id = body.get("merchant_id")
        candidates = BuyerAgent(MerchantAgent()).candidates(db, parsed, merchant_id)
        row = (
            db.execute(
                text(
                    "insert into intents(user_id,raw_text,parsed_payload,parser_provider,parser_model,parser_version,schema_version) values(:u,:raw,cast(:payload as jsonb),:provider,:model,:version,'1.0') returning id"
                ),
                {
                    "u": user.id,
                    "raw": context_text,
                    "payload": parsed.model_dump_json(),
                    "provider": model_trace["provider"],
                    "model": model_trace["model"],
                    "version": model_trace["task"],
                },
            )
            .mappings()
            .one()
        )
        answer = {
            "status": "REQUIRES_MANDATE_CONFIRMATION",
            "parsed_intent": parsed.model_dump(mode="json"),
            "intent_id": str(row["id"]),
            "candidates": candidates,
            "tool_call": "MerchantAgent.catalog_search",
            "provenance": {
                "intent": "MODEL_DERIVED",
                "authority_constraints": "SYSTEM_DERIVED",
                "products": "MERCHANT_CATALOG",
            },
            "model_call": model_trace,
        }
        # Log missed searches as market demand for merchant intelligence
        if not candidates and parsed and parsed.product_query:
            estimated_price = parsed.max_budget_minor if parsed.max_budget_minor else None
            db.execute(
                text(
                    """insert into market_demand(product_query, estimated_price_minor, currency, merchant_id, search_count)
                       values(:query, :price, :currency, :merchant_id, 1)
                       on conflict (product_query, merchant_id) do update
                       set search_count = market_demand.search_count + 1,
                           last_searched_at = now(),
                           estimated_price_minor = coalesce(:price, market_demand.estimated_price_minor)"""
                ),
                {
                    "query": parsed.product_query.strip().lower(),
                    "price": estimated_price,
                    "currency": parsed.currency or "INR",
                    "merchant_id": merchant_id,
                },
            )
    db.execute(
        text(
            "insert into conversation_messages(thread_id,role,content,payload,source_category) values(:t,'ASSISTANT',:content,cast(:payload as jsonb),'SYSTEM_DERIVED')"
        ),
        {"t": thread_id, "content": answer["status"], "payload": json.dumps(answer, default=str)},
    )
    db.commit()
    if parsed and candidates:
        AuditLedgerService().append(
            db,
            scope=f"SESSION:{thread_id}",
            event_type="PRODUCT_DISCOVERED",
            actor="BUYER_AGENT",
            payload={"candidate_ids": [str(item["product_id"]) for item in candidates]},
            user_id=user.id,
        )
        db.commit()
    return answer


from pydantic import BaseModel, Field

class MarketIntelligenceResult(BaseModel):
    source: str = Field(description="Name of the platform (e.g. Amazon, Flipkart, OLX)")
    price_minor: int = Field(description="Price in minor units (paise), e.g. 1999900 for ₹19,999")
    currency: str = Field(default="INR")
    capability: str = Field(default="Scout / External", description="Must be 'Scout / External' or 'Manual / Unverified'")
    url: str = Field(description="A realistic URL for the product on this platform")

class MarketIntelligenceResponse(BaseModel):
    results: list[MarketIntelligenceResult] = Field(description="List of 5 competitor market prices")

@router.get("/market-intelligence")
async def get_market_intelligence(
    query: str,
    db: Session = Depends(get_db_session),
    gateway: ModelGateway = Depends(get_intent_model_gateway)
):
    norm_query = query.lower().strip()
    
    rows = db.execute(
        text("""
            SELECT connector, price_minor, currency, capability, source_url
            FROM external_offer_snapshots
            WHERE normalized_product_key ILIKE :q
               OR title ILIKE :q
            ORDER BY price_minor ASC
        """),
        {"q": f"%{norm_query}%"}
    ).fetchall()
    
    results = []
    for row in rows:
        results.append({
            "source": row[0],
            "price_minor": row[1],
            "currency": row[2],
            "capability": row[3],
            "url": row[4]
        })
        
    if not results:
        # User requested LLM live search fallback for realistic values
        prompt = (
            f"You are an internet market intelligence agent. We need realistic historical market prices from the last 24 hours for the product '{query}'. "
            "Return 5 platforms where this is commonly sold. Choose the platforms dynamically based on the product category "
            "(e.g., use Swiggy/Blinkit/Zomato for food/ice cream, Croma/Reliance Digital for electronics, Myntra/Ajio for fashion, etc.). "
            "Always include Amazon and Flipkart. For one platform, use OLX with 'Manual / Unverified' as capability. The others should be 'Scout / External'. "
            "Ensure price_minor is a realistic price in paise (rupees * 100)."
        )
        try:
            parsed, _ = await gateway.parse(prompt, MarketIntelligenceResponse)
            results = [r.model_dump() for r in parsed.results]
            
            # Optionally cache these generated results in DB so next time it's faster
            from uuid import uuid4
            from datetime import datetime, timezone
            run_id = uuid4()
            now = datetime.now(timezone.utc)
            for r in results:
                db.execute(
                    text(
                        "insert into external_offer_snapshots(id, run_id, connector, capability, external_offer_id, normalized_product_key, title, price_minor, currency, source_url, fetched_at) "
                        "values(:id, :run, :connector, :cap, :ext, :key, :title, :price, :curr, :url, :now)"
                    ),
                    {
                        "id": uuid4(),
                        "run": run_id,
                        "connector": r["source"],
                        "cap": r["capability"],
                        "ext": str(uuid4()),
                        "key": norm_query,
                        "title": query,
                        "price": r["price_minor"],
                        "curr": r["currency"],
                        "url": r["url"],
                        "now": now
                    }
                )
            db.commit()
        except Exception as e:
            print(f"LLM fallback failed: {e}")
            pass

    return {"results": results}
