# Post-Quantum Cryptography (PQC) Roadmap

## Strategic Vision
Valdrix is committed to future-proofing tenant data against the "Harvest Now, Decrypt Later" threat. This roadmap outlines the transition from classical asymmetric cryptography (RSA, ECC) to NIST-standardized quantum-resistant algorithms.

## 1. Cryptographic Inventory (Current State)
- **Symmetric**: AES-256-CBC (Fernet) - *Quantum-Safe (requires 256-bit keys)*.
- **Hashing**: SHA-256 / HMAC-SHA-256 - *Quantum-Safe*.
- **KDF**: PBKDF2-SHA256 - *Quantum-Safe (with high iteration counts)*.
- **Asymmetric**: RSA/ECC used in JWT and external TLS - *Quantum-Vulnerable*.

## 2. PQC Migration Strategy (2025-2027)

### Phase 1: Cryptographic Agility (Q1-Q2 2026)
- [x] Centralize all key derivation in `EncryptionKeyManager`.
- [ ] Abstract `Fernet` usage to allow for pluggable encryption backends (e.g., swapping to AES-GCM or NIST PQC candidates).

### Phase 2: Hybrid Signatures (Q3-Q4 2026)
- Research integration of **ML-KEM (Kyber)** and **ML-DSA (Dilithium)** for internal service-to-service communication.
- Evaluate AWS/Google Cloud KMS offerings for hybrid post-quantum key exchange.

### Phase 3: PQC Native (2027+)
- Full migration of static data encryption to NIST-finalized post-quantum standards.
- Update blind indexing logic to incorporate lattice-based PRFs if standardized.

## 3. Compliance & Standards
- Adhere to **FIPS 203, 204, and 205** standards once finalized.
- Monitor **NIST Special Publication 800-208** for stateful hash-based signatures.

## 4. Operational Risk Mitigation
- **Key Rotation**: Already implemented in `EncryptionKeyManager` to support seamless algorithm migration.
- **Performance**: Monitor CPU overhead during transition from ECC to ML-KEM, as PQC signatures are significantly larger.
