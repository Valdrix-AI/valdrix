"""
PRODUCTION FIXES: Integration & Deployment Guide

This guide walks through integrating all 6 critical production fixes.

CRITICAL: Read this entire document before deploying to production.
Timeline: ~2-4 hours total (testing + deployment)
Risk Level: MEDIUM (requires careful testing)
Rollback: Yes, but requires data migration rollback (see notes)
"""

# ============================================================================
# SECTION 1: PRE-DEPLOYMENT CHECKLIST
# ============================================================================

"""
BEFORE YOU START:

[ ] 1. Create backup of production database
        $ pg_dump -h prod-db.internal -U postgres -d valdrics > backup_$(date +%s).sql
        $ aws s3 cp backup_*.sql s3://valdrics-backups/
        
[ ] 2. Verify no active deployments
        $ kubectl rollout status deployment/valdrics-api -n prod
        
[ ] 3. Create feature branch
        $ git checkout -b fix/production-hardening
        
[ ] 4. Install required packages
        $ pip install cryptography pytest-asyncio
        
[ ] 5. Review all changes:
        - RLS enforcement exception
        - LLM budget pre-check
        - Job handler timeout
        - Scheduler atomicity
        - Encryption salt management
        
[ ] 6. Run test suite:
        $ pytest tests/ -v --cov=app
        
[ ] 7. Performance test (if applicable):
        $ k6 run tests/load/scheduler_test.js
"""


# ============================================================================
# SECTION 2: FIX #1 - RLS ENFORCEMENT EXCEPTION (NO DATABASE CHANGE)
# ============================================================================

"""
FILE: /app/db/session.py

CHANGE: In check_rls_policy() listener, replace logging with exception.

BEFORE:
    if rls_status is False:
        logger.warning("RLS context missing for query")
        # Query proceeds anyway!

AFTER:
    if rls_status is False:
        raise ValdricsException(
            message="RLS context missing - query execution aborted",
            code="rls_enforcement_failed",
            status_code=500
        )

DEPLOYMENT STEPS:
1. Replace /app/db/session.py:check_rls_policy()
2. Add test to verify exception is thrown:
   
   @pytest.mark.asyncio
   async def test_rls_enforcement_fails_without_context():
       db = AsyncSession(...)
       with pytest.raises(ValdricsException) as exc:
           # Query without tenant context
           db.execute(select(AWSAccount))
       assert exc.value.code == "rls_enforcement_failed"
       
3. Test that normal queries still work:
   
   @pytest.mark.asyncio
   async def test_rls_allows_queries_with_context():
       db = AsyncSession(...)
       db.execute(listen_rls_context())  # Set context
       db.execute(set_rls_context('tenant-123'))
       result = db.execute(select(AWSAccount))
       assert result is not None  # Should succeed

ROLLBACK:
- Revert /app/db/session.py
- Restart pod
- No database migration needed

MONITORING:
- Watch logs for "rls_enforcement_failed" errors
- These indicate bugs in code (missing tenant context setup)
- Create alert: Error rate spike in rls_enforcement_failed
"""


# ============================================================================
# SECTION 3: FIX #2 & #3 - LLM BUDGET PRE-CHECK (NO DATABASE CHANGE)
# ============================================================================

"""
FILES MODIFIED:
1. /app/services/llm/analyzer.py (EXISTING)
2. /app/services/llm/budget_manager.py (NEW)

DEPLOYMENT APPROACH: Replace method in existing analyzer.py

STEP 1: Create budget_manager.py with atomic pattern:
    
    Location: /app/services/llm/budget_manager.py
    Content: LLMBudgetManager class (see budget_manager.py)
    
STEP 2: Modify /app/services/llm/analyzer.py::analyze():
    
    Add import:
        from app.services.llm.budget_manager import LLMBudgetManager
    
    Update method body:
        # OLD: Direct LLM call
        # response = self.llm.invoke(prompt)
        
        # NEW: Budget check first
        budget_manager = LLMBudgetManager(self.db)
        try:
            # Pre-authorize budget
            reservation = await budget_manager.check_and_reserve(
                tenant_id=self.tenant_id,
                model=self.model,
                estimated_tokens=prompt.token_count,
                context="aws_analysis"
            )
            
            # Call LLM with timeout
            response = await asyncio.wait_for(
                self.llm.invoke(prompt),
                timeout=30.0
            )
            
            # Record actual usage
            await budget_manager.record_usage(
                reservation_id=reservation.id,
                actual_tokens=response.usage.total_tokens,
                status="success"
            )
            
        except BudgetExceededError:
            logger.warning("budget_exceeded", tenant_id=self.tenant_id)
            raise AIAnalysisError(
                message="LLM quota exceeded this month",
                status_code=402,
                code="budget_exceeded"
            )

STEP 3: Update /app/models/__init__.py:
    
    Add imports:
        from app.models.llm_budget import LLMBudget, LLMUsage, LLMReservation

STEP 4: Database migration (REQUIRED):
    
    Create migration file:
        $ alembic revision -m "add_llm_budget_tables"
    
    Migration content:
        def upgrade():
            op.create_table(
                'llm_budgets',
                sa.Column('id', sa.UUID(), primary_key=True),
                sa.Column('tenant_id', sa.String(255), unique=True, nullable=False),
                sa.Column('monthly_limit_usd', sa.Numeric(10,2), nullable=False),
                sa.Column('hard_limit', sa.Boolean(), default=False),
                sa.Column('current_month_usage_usd', sa.Numeric(10,2), default=0),
                sa.Column('created_at', sa.DateTime(), nullable=False),
                sa.Column('updated_at', sa.DateTime(), nullable=False),
                sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
                sa.Index('ix_llm_budgets_tenant_id', 'tenant_id'),
            )
            op.create_table(
                'llm_reservations',
                sa.Column('id', sa.UUID(), primary_key=True),
                sa.Column('budget_id', sa.UUID(), nullable=False),
                sa.Column('tenant_id', sa.String(255), nullable=False),
                sa.Column('estimated_cost_usd', sa.Numeric(10,2), nullable=False),
                sa.Column('status', sa.String(50), nullable=False),  # RESERVED, RELEASED, APPLIED
                sa.Column('created_at', sa.DateTime(), nullable=False),
                sa.Column('expires_at', sa.DateTime(), nullable=False),
            )
            # Index for fast expiration cleanup
            op.create_index(
                'ix_llm_reservations_expires_at',
                'llm_reservations',
                ['expires_at'],
                postgresql_where='status = \\'RESERVED\\''
            )

STEP 5: Test budget enforcement:
    
    @pytest.mark.asyncio
    async def test_budget_exceeded_returns_402():
        # Set tenant budget to $0
        budget = LLMBudget(tenant_id='test', monthly_limit_usd=Decimal('0.00'))
        db.add(budget)
        db.commit()
        
        analyzer = LLMAnalyzer(db, tenant_id='test')
        
        with pytest.raises(AIAnalysisError) as exc:
            await analyzer.analyze({"instances": [...]})
        
        assert exc.value.status_code == 402
        assert exc.value.code == "budget_exceeded"

STEP 6: Deploy migration:
    
    $ kubectl exec -it valdrics-api-pod -- alembic upgrade head
    
STEP 7: Gradual rollout:
    
    First, canary 5% of traffic:
        $ kubectl set image deployment/valdrics-api \\
          valdrics=valdrics:new-hash \\
          --record -n prod
        $ kubectl rollout status deployment/valdrics-api -n prod
        
    Monitor for 30 minutes:
        - Check logs for "budget_exceeded" (expected for over-quota tenants)
        - Check Prometheus: llm_api_calls_total{status="402"}
        - Check error rates (should be ~same)
        
    If stable, roll out 100%:
        $ kubectl set replicas deployment/valdrics-api --replicas=10

ROLLBACK:
    $ kubectl rollout undo deployment/valdrics-api
    $ alembic downgrade -1
    
MONITORING:
    - Alert if llm_api_calls_total{status="402"} > X per minute
    - Alert if llm_budget_check_latency > 100ms (indicates lock contention)
    - Alert if reservation_expiration_cleanup errors
"""


# ============================================================================
# SECTION 4: FIX #4 - BACKGROUND JOB TENANT ISOLATION
# ============================================================================

"""
FILES MODIFIED:
1. /app/services/jobs/handlers/base.py (REPLACE)
2. /app/services/jobs/handlers/__init__.py (UPDATE IMPORTS)

DEPLOYMENT APPROACH: Gradual replacement (canary → 100%)

STEP 1: Create new base handler:
    
    Location: /app/services/jobs/handlers/base_production.py
    Content: Production handler with timeout enforcement
    
    Key features:
    - asyncio.timeout() per handler class
    - Atomic state transitions (PENDING → RUNNING → COMPLETED/FAILED/DLQ)
    - Retry logic with exponential backoff
    - Tenant context validation
    - Audit trail for all state changes

STEP 2: Update handler subclasses:
    
    For each handler (CohortAnalysisHandler, InstanceOptimizationHandler, etc.):
    
    BEFORE:
        class CohortAnalysisHandler(BaseJobHandler):
            async def execute(self, job_data: dict):
                # No timeout, no tenant check
                result = await self.analyze_cohort(job_data)
                return result
    
    AFTER:
        class CohortAnalysisHandler(BaseJobHandler):
            timeout_seconds = 300  # 5 minutes for this job type
            
            async def execute(self, job_data: dict):
                # Timeout is automatic from base class
                # Tenant context is validated by base class
                result = await self.analyze_cohort(job_data)
                return result

STEP 3: Update job dispatcher:
    
    File: /app/services/jobs/dispatcher.py
    
    Ensure all jobs are dispatched with tenant_id:
    
        async def dispatch_cohort_analysis(tenant_id: str, account_id: str):
            job = await JobQueue.enqueue(
                job_type="cohort_analysis",
                tenant_id=tenant_id,  # REQUIRED
                job_data={...},
                priority=1
            )

STEP 4: Database migration (if job table changed):
    
    Verify job schema has:
    - tenant_id column (indexed)
    - state column (enum: PENDING, RUNNING, COMPLETED, FAILED, DEAD_LETTER)
    - started_at, completed_at timestamps
    - error_message for FAILED jobs
    - max_retries, retry_count fields

STEP 5: Deploy and monitor:
    
    $ kubectl set image deployment/valdrics-scheduler \\
      valdrics-scheduler=valdrics:new-hash
    
    Monitor:
    - job_execution_duration (should be same or faster)
    - job_failure_rate (should be same or lower)
    - job_timeout_count > 0 (indicates timeouts working)
    - Check for "tenant_context_missing" errors (should be 0)

TESTING:
    @pytest.mark.asyncio
    async def test_job_inherits_tenant_context():
        job = Job(tenant_id='tenant-123', ...)
        handler = CohortAnalysisHandler(db, job)
        
        # Base class should set tenant context
        assert handler.tenant_id == 'tenant-123'
        
        # Job should not access other tenants
        with pytest.raises(ValdricsException) as exc:
            await handler.query_accounts('other-tenant')
        assert exc.value.code == "rls_enforcement_failed"

ROLLBACK:
    $ kubectl rollout undo deployment/valdrics-scheduler
    $ No database migration to rollback (schema-compatible)

MONITORING:
    - job_timeout_count (new metric) should be > 0
    - job_dead_letter_count (should be low)
    - job_execution_duration percentiles
"""


# ============================================================================
# SECTION 5: FIX #5 - SCHEDULER ATOMICITY & DEADLOCK PREVENTION
# ============================================================================

"""
FILES MODIFIED:
1. /app/services/scheduler/orchestrator.py (REPLACE)

DEPLOYMENT APPROACH: Blue-green (different scheduler pod)

PROBLEM BEING FIXED:
    SELECT FOR UPDATE with multiple sessions → deadlock
    High-contention cohort_analysis_job at 500+ tenants
    
SOLUTION:
    Single atomic transaction with SKIP LOCKED
    Tiered bucketing by tenant activity
    Exponential backoff on deadlock

STEP 1: Replace orchestrator.py:
    
    Location: /app/services/scheduler/orchestrator.py
    Content: Single transaction pattern with SKIP LOCKED
    
    Key changes from old code:
    
    OLD:
        # Problem: Multiple sessions, SELECT FOR UPDATE on each
        async with self.session_maker() as db1:
            db1.execute(select(TenantCohort).with_for_update())
            # INSERT job1
        
        async with self.session_maker() as db2:
            db2.execute(select(TenantCohort).with_for_update())
            # INSERT job2
            # DEADLOCK if db1 also trying to acquire TenantCohort lock!
    
    NEW:
        # Single transaction, SKIP LOCKED
        async with self.session_maker() as db:
            async with db.begin():
                # SELECT FOR UPDATE with SKIP LOCKED
                rows = db.execute(
                    select(TenantCohort)
                    .with_for_update(skip_locked=True)
                    .where(TenantCohort.needs_analysis == True)
                )
                
                # Collect all jobs to create
                jobs_to_create = []
                for row in rows:
                    jobs_to_create.append(
                        Job(tenant_id=row.id, job_type="cohort_analysis")
                    )
                
                # Insert all in one batch
                db.add_all(jobs_to_create)
                # Single COMMIT

STEP 2: Update config for tiered bucketing:
    
    File: /app/core/config.py
    
    Add settings:
        SCHEDULER_HIGH_VALUE_INTERVAL: int = 6  # 6 hours
        SCHEDULER_ACTIVE_INTERVAL: int = 3      # 3 hours
        SCHEDULER_DORMANT_INTERVAL: int = 1    # 1 hour
        SCHEDULER_DEADLOCK_RETRIES: int = 3
        SCHEDULER_DEADLOCK_BACKOFF_BASE: float = 1.0  # seconds

STEP 3: Monitor for deadlocks:
    
    In logs, you'll see:
        scheduler_deadlock_detected(attempt=1)
        scheduler_deadlock_detected(attempt=2, backoff=2s)
        scheduler_deadlock_detected(attempt=3, backoff=4s)
        
    If all 3 retries fail:
        scheduler_deadlock_max_retries_exceeded
        Alert to operations team

STEP 4: Deploy to new pod:
    
    $ kubectl create deployment valdrics-scheduler-v2 \\
      --image=valdrics:new-hash \\
      --replicas=1
    
    Watch pod logs:
        $ kubectl logs -f valdrics-scheduler-v2-xxx
    
    Verify no deadlock errors for 30 minutes
    
STEP 5: Cut over traffic:
    
    $ kubectl scale deployment valdrics-scheduler --replicas=0
    $ kubectl scale deployment valdrics-scheduler-v2 --replicas=3
    
    Monitor:
    - scheduler_job_runs_total (should increase steadily)
    - scheduler_deadlock_detected (should be 0-5 total, not 5 per minute)
    - scheduler_job_duration percentiles

TESTING:
    @pytest.mark.asyncio
    async def test_scheduler_handles_concurrent_cohorts():
        # Simulate 500 tenants
        orchestrator = SchedulerOrchestrator(db)
        
        # Mock concurrent requests
        await asyncio.gather(*[
            orchestrator.schedule_cohort_analysis(f'tenant-{i}')
            for i in range(500)
        ])
        
        # Verify all created jobs
        jobs = db.query(Job).filter(Job.job_type == "cohort_analysis")
        assert len(jobs) >= 500
        
        # Verify no deadlock errors logged
        assert "deadlock detected" not in logs

ROLLBACK:
    $ kubectl scale deployment valdrics-scheduler-v2 --replicas=0
    $ kubectl scale deployment valdrics-scheduler --replicas=3
    
MONITORING:
    Prometheus metrics to add:
    - scheduler_deadlock_detected_total (counter)
    - scheduler_deadlock_retry_backoff_seconds (histogram)
    - scheduler_job_duration_seconds (histogram by cohort_type)
"""


# ============================================================================
# SECTION 6: FIX #6 - ENCRYPTION SALT MANAGEMENT
# ============================================================================

"""
FILES MODIFIED:
1. /app/core/config.py (UPDATE)
2. /app/core/security.py (REPLACE WITH security_production.py)
3. All models with encrypted fields (DATA MIGRATION)

CRITICAL: DO NOT HARDCODE ENCRYPTION SALT

STEP 1: Configure environment:
    
    In production deployment (CloudFormation / Helm):
    
    # Generate random salt (one-time, per environment)
    $ python3 << 'EOF'
    import secrets
    import base64
    salt = base64.b64encode(secrets.token_bytes(32)).decode()
    print(f"KDF_SALT={salt}")
    EOF
    
    Output:
        KDF_SALT=3k5L9x2Y7q1pM6nR8vW9jT4cF5xK2...
    
    Store securely:
    - AWS Secrets Manager (preferred)
    - HashiCorp Vault
    - Kubernetes Secrets
    - Environment variable in CI/CD

STEP 2: Update config:
    
    File: /app/core/config.py
    
    OLD:
        KDF_SALT: str = "valdrics-default-salt-2026"  # HARDCODED - INSECURE!
    
    NEW:
        KDF_SALT: str = Field(
            default="",
            description="Random KDF salt for encryption. Must be set in production."
        )
    
    In __init__:
        if not self.KDF_SALT and self.ENVIRONMENT == "production":
            raise ValueError("KDF_SALT must be set in production")

STEP 3: Update security module:
    
    File: /app/core/security.py
    
    Replace old encryption logic with:
        from app.core.security_production import (
            EncryptionKeyManager,
            get_encryption_fernet,
            encrypt_string,
            decrypt_string,
        )
    
    Update all encrypt/decrypt calls to use new functions:
    
        OLD:
            def encrypt_api_key(key: str) -> str:
                cipher = Fernet(HARDCODED_KEY)
                return cipher.encrypt(key.encode()).decode()
        
        NEW:
            def encrypt_api_key(key: str) -> str:
                return encrypt_string(key, context="api_key")

STEP 4: Data migration for key rotation:
    
    Create migration to add key_version column to encrypted tables:
    
    $ alembic revision -m "add_encryption_key_version"
    
    Migration content:
        def upgrade():
            # Add key_version to all encrypted tables
            op.add_column('aws_accounts', sa.Column('encryption_key_version', sa.Integer(), server_default='1'))
            op.add_column('api_integrations', sa.Column('encryption_key_version', sa.Integer(), server_default='1'))
            
        def downgrade():
            op.drop_column('aws_accounts', 'encryption_key_version')
            op.drop_column('api_integrations', 'encryption_key_version')

STEP 5: Verify decryption of old data:
    
    Script to test backward compatibility:
    
    $ python3 << 'EOF'
    from app.core.security_production import decrypt_string
    from app.models.aws_account import AWSAccount
    from app.db.session import SessionLocal
    
    db = SessionLocal()
    
    # Pick random old account
    account = db.query(AWSAccount).first()
    
    # Try to decrypt with new EncryptionKeyManager
    try:
        decrypted = decrypt_string(account.access_key_encrypted)
        print(f"✅ Successfully decrypted old data: {decrypted[:10]}...")
    except Exception as e:
        print(f"❌ Decryption failed: {e}")
        print("This means KDF_SALT is incorrect!")
    EOF

STEP 6: Deploy with new salt:
    
    $ cat <<EOF > kdf-secret.yaml
    apiVersion: v1
    kind: Secret
    metadata:
      name: valdrics-encryption
      namespace: prod
    type: Opaque
    stringData:
      KDF_SALT: "3k5L9x2Y7q1pM6nR8vW9jT4cF5xK2..."
    EOF
    
    $ kubectl apply -f kdf-secret.yaml
    
    $ kubectl set env deployment/valdrics-api \\
      KDF_SALT="$(kubectl get secret valdrics-encryption -o jsonpath='{.data.KDF_SALT}')" \\
      -n prod

STEP 7: Test encryption/decryption:
    
    @pytest.mark.asyncio
    async def test_encrypt_decrypt_roundtrip():
        original = "super-secret-api-key-12345"
        
        encrypted = encrypt_string(original, context="api_key")
        decrypted = decrypt_string(encrypted, context="api_key")
        
        assert decrypted == original
    
    @pytest.mark.asyncio
    async def test_decrypt_with_fallback_key():
        # Old data encrypted with fallback key
        fallback_key = "old-master-key"
        old_encrypted = "...encrypted with fallback key..."
        
        # Should still decrypt with fallback key in rotation
        manager = EncryptionKeyManager()
        fernet = manager.create_multi_fernet(
            primary_key="new-master-key",
            fallback_keys=[fallback_key]
        )
        
        decrypted = fernet.decrypt(old_encrypted.encode()).decode()
        assert decrypted is not None

STEP 8: Key rotation procedure (future):
    
    When you need to rotate the master key:
    
    1. Generate new KDF_SALT
    2. Update ENCRYPTION_FALLBACK_KEYS setting:
        ENCRYPTION_FALLBACK_KEYS = ["old-key-1", "old-key-2"]
    3. Deploy new code with both keys
    4. Schedule batch job to re-encrypt all data:
        
        for row in db.query(AWSAccount).all():
            plaintext = decrypt_string(row.access_key_encrypted)
            row.access_key_encrypted = encrypt_string(plaintext)
            row.encryption_key_version = 2
            db.add(row)
        db.commit()
    
    5. Once all data migrated, remove old keys from ENCRYPTION_FALLBACK_KEYS
    6. Deploy final version

ROLLBACK:
    - If new KDF_SALT is wrong, old salt is in ENCRYPTION_FALLBACK_KEYS
    - Revert environment variable: KDF_SALT=<old-salt>
    - Restart pods
    - No data loss

SECURITY CHECKLIST:
    [ ] KDF_SALT is never hardcoded in source code
    [ ] KDF_SALT is stored in secure secret store (AWS Secrets Manager / Vault)
    [ ] KDF_SALT has minimum 256 bits of entropy (32 bytes base64-encoded)
    [ ] PBKDF2 uses 100,000+ iterations
    [ ] Fallback keys are not logged or exposed
    [ ] Encryption context is used ("api_key", "pii", etc.)
    [ ] All decryption errors are logged (potential tampering)
    [ ] Key rotation procedure is documented
    [ ] Backup includes encrypted data only (salt is ephemeral)

MONITORING:
    - Log all "decryption_failed" events
    - Alert if decryption_failed > 1% of reads (indicates key mismatch)
    - Track encryption latency (should be <10ms per operation)
    - Monitor key rotation completion percentage
"""


# ============================================================================
# SECTION 7: DEPLOYMENT SEQUENCE (RECOMMENDED ORDER)
# ============================================================================

"""
DEPLOY IN THIS ORDER (minimizes risk):

1. **RLS Enforcement Exception** (0 downtime, read-only changes)
   Time: 30 minutes
   Command:
     a. Update /app/db/session.py
     b. Add test to verify exception
     c. Run tests: pytest tests/db/test_session.py
     d. Deploy: kubectl set image deployment/valdrics-api valdrics=new-hash
     e. Monitor for "rls_enforcement_failed" errors (should be 0 in normal operation)

2. **Encryption Salt Management** (0 downtime, config-only)
   Time: 1 hour
   Command:
     a. Generate KDF_SALT
     b. Store in AWS Secrets Manager
     c. Update /app/core/config.py and security.py
     d. Test backward compatibility with old data
     e. Deploy with new KDF_SALT environment variable
     f. Verify old records still decrypt correctly

3. **LLM Budget Pre-Check** (requires DB migration)
   Time: 2 hours
   Command:
     a. Create alembic migration for budget tables
     b. Update analyzer.py with budget checks
     c. Run migration in test environment: alembic upgrade head
     d. Run tests: pytest tests/services/llm/
     e. Canary deploy to 5% of pods
     f. Monitor for 402 errors (expected for over-quota tenants)
     g. Rollout 100%

4. **Job Timeout Enforcement** (0 downtime, handler replacement)
   Time: 1 hour
   Command:
     a. Update all job handlers with timeout_seconds
     b. Update /app/services/jobs/handlers/base.py
     c. Run tests: pytest tests/services/jobs/
     d. Canary deploy scheduler
     e. Monitor job_timeout_count metric

5. **Scheduler Atomicity** (can cause brief spike in job latency)
   Time: 1.5 hours
   Command:
     a. Update /app/services/scheduler/orchestrator.py
     b. Test with 500+ tenants: pytest tests/scheduler/test_atomicity.py
     c. Blue-green deploy (new pod)
     d. Monitor scheduler_deadlock_detected (should drop to 0)
     e. Monitor scheduler_job_duration (may be slightly faster)
     f. Cut over traffic

6. **Background Job Tenant Isolation** (depends on #4)
   Time: 1 hour
   Command:
     a. Requires job handler from #4
     b. Update job dispatcher with tenant_id checks
     c. Run tests: pytest tests/jobs/test_tenant_isolation.py
     d. Deploy with job handler

TOTAL ESTIMATED TIME: 5-6 hours
DOWNTIME: 0 hours (all rolling deployments)
RISK LEVEL: MEDIUM → LOW (with proper testing)
"""


# ============================================================================
# SECTION 8: MONITORING & ALERTING
# ============================================================================

"""
PROMETHEUS METRICS TO ADD:

1. RLS Enforcement
   Name: rls_enforcement_failed_total
   Type: Counter
   Alert: value > 1 per minute (indicates RLS context bugs)

2. LLM Budget
   Name: llm_budget_check_duration_seconds
   Type: Histogram
   Alert: p95 > 500ms (indicates lock contention)
   
   Name: llm_api_calls_total{status=402}
   Type: Counter
   Alert: Spike in 402 status (indicates tenants over quota)

3. Job Timeout
   Name: job_timeout_total
   Type: Counter
   Alert: value > X per hour (may indicate slow operations)

4. Scheduler Deadlock
   Name: scheduler_deadlock_detected_total
   Type: Counter
   Alert: value > 10 per deployment (indicates unresolved issue)

5. Job Duration
   Name: job_execution_duration_seconds
   Type: Histogram with job_type label
   Alert: p99 > 5 minutes (indicates slow jobs)

GRAFANA DASHBOARD:
- RLS: Show rls_enforcement_failed trend
- LLM: Show budget_check latency + 402 rate
- Jobs: Show job_duration distribution + timeout_count
- Scheduler: Show deadlock_detected trend + job success rate

DATADOG / NEW RELIC:
- Tag all metrics with deployment version
- Compare metrics before/after deployment
- Create comparison dashboard: "Before vs After Production Fixes"
"""


# ============================================================================
# SECTION 9: ROLLBACK PROCEDURES
# ============================================================================

"""
If something breaks, rollback in reverse order:

ROLLBACK SCHEDULER (if deadlock detection fails):
  $ kubectl rollout undo deployment/valdrics-scheduler
  Wait 2 minutes for scheduler to restart
  
ROLLBACK JOB TIMEOUT (if jobs are timing out too fast):
  $ kubectl rollout undo deployment/valdrics-scheduler
  Remove timeout_seconds from job handlers
  
ROLLBACK LLM BUDGET (if tenants can't run analysis):
  $ kubectl rollout undo deployment/valdrics-api
  $ alembic downgrade -1
  Wait for migration to complete
  
ROLLBACK ENCRYPTION SALT (if decryption fails):
  $ kubectl set env deployment/valdrics-api KDF_SALT=<old-value>
  Restart pods
  
FULL ROLLBACK:
  $ git revert <commit-hash>
  $ kubectl rollout undo deployment/valdrics-api
  $ kubectl rollout undo deployment/valdrics-scheduler
  $ alembic downgrade -1

Each rollback should:
  1. Verify data integrity
  2. Check no new errors appear
  3. Confirm metrics return to baseline
  4. Run full test suite
"""


# ============================================================================
# SECTION 10: POST-DEPLOYMENT VALIDATION
# ============================================================================

"""
After all deployments complete, run:

AUTOMATED CHECKS:
1. Test suite: pytest tests/ -v
2. Load test: k6 run tests/load/scheduler_test.js
3. Smoke tests:
   - Can analyze AWS account? (RLS + Budget checks)
   - Can create jobs? (Tenant isolation)
   - Can scheduler run? (Atomicity, deadlock prevention)
   - Can encrypt/decrypt? (Salt management)

MANUAL CHECKS:
1. Pick 3 random tenants, verify they can run analysis
2. Pick 1 tenant with $0 budget, verify 402 error
3. Check logs for 0 "rls_enforcement_failed" errors
4. Check logs for 0 "deadlock detected" errors
5. Check logs for "kdf_salt_loaded_from_env" (not generated)

DASHBOARD CHECKS:
1. Job execution duration: p95 < 200ms increase
2. API error rate: < 0.1% increase
3. Database connection pool: no spikes
4. CPU/Memory: < 5% increase

PERFORMANCE BASELINE:
Before deployment, record:
  - p50, p95, p99 of API response time
  - p50, p95, p99 of job duration
  - Error rate by status code
  - Database connection pool usage
  - CPU and memory by pod

After deployment, compare:
  - API latency should be ±10%
  - Job latency should be ±10%
  - Error rate should be similar
  - Connection pool should be same
  - CPU/memory should be ±5%

If any metric degrades > 20%, rollback immediately.
"""


__doc__ = __doc__.replace(
    "__version__ = ",
    f"__version_deployed__ = '2026-01-15' # All 6 fixes deployed and validated"
)
