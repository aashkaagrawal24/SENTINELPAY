import asyncio
import logging

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.services.campaign_services import CampaignOrchestrator

logger = logging.getLogger(__name__)


async def campaign_scheduler(settings: Settings) -> None:
    """Prototype scheduler; production should move this cycle to a durable worker."""
    engine = create_engine(settings.supabase_database_url.get_secret_value(), pool_pre_ping=True)
    while True:
        await asyncio.sleep(settings.campaign_scan_interval_minutes * 60)
        try:
            with Session(engine) as db:
                result = await asyncio.to_thread(
                    CampaignOrchestrator.run_cycle,
                    db,
                    settings.campaign_inventory_pressure_threshold,
                    settings.campaign_score_weights,
                )
                logger.info("campaign scan complete result=%s", result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("scheduled campaign scan failed")
