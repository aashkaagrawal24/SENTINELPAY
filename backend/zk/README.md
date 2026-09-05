# Budget Sufficiency Groth16 Circuit

The circuit proves the narrow claim `PrivateBudget >= PublicPrice` for unsigned 32-bit minor-unit values. `privateBudget` is a private witness; `publicPrice` and the `sufficient=1` output are public.

The checked-in proving artifacts are for controlled Test Mode demonstration. They are not a claim of a multi-party production ceremony or third-party audit.

```powershell
npm install
npm run compile
npx snarkjs powersoftau new bn128 12 build/pot12_0000.ptau -v
npx snarkjs powersoftau contribute build/pot12_0000.ptau build/pot12_0001.ptau --name="SentinelPay controlled setup" -e="sentinelpay-v4.2-controlled-entropy"
npx snarkjs powersoftau prepare phase2 build/pot12_0001.ptau build/pot12_final.ptau -v
npx snarkjs groth16 setup build/budget_sufficiency.r1cs build/pot12_final.ptau build/budget_sufficiency_0000.zkey
npx snarkjs zkey contribute build/budget_sufficiency_0000.zkey build/budget_sufficiency_final.zkey --name="SentinelPay controlled contribution" -e="sentinelpay-v4.2-zkey-entropy"
npx snarkjs zkey export verificationkey build/budget_sufficiency_final.zkey build/verification_key.json
```
