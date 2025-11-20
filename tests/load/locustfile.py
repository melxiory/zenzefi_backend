"""
Locust Load Testing Suite for Zenzefi Backend

Tests system performance under various load scenarios.
Simulates realistic user behavior with registration, token purchase, and proxy usage.

Usage:
    # Interactive mode (Web UI)
    locust -f tests/load/locustfile.py --host http://localhost:8000

    # Headless mode (automated)
    locust -f tests/load/locustfile.py --host http://localhost:8000 \
           --users 100 --spawn-rate 10 --run-time 5m --headless

Performance Targets:
    - Throughput: 1000 requests/second (sustained)
    - p50 latency: < 50ms
    - p95 latency: < 200ms
    - p99 latency: < 500ms
    - Error rate: < 0.1% under normal load
"""
import secrets
import random
from locust import HttpUser, task, between, events
from loguru import logger


class ZenzefiUser(HttpUser):
    """
    Simulates a realistic Zenzefi user workflow

    Workflow:
    1. Register new account
    2. Login to get JWT token
    3. Purchase balance (mock)
    4. Purchase access token
    5. Use access token for proxy requests
    6. Check balance and transactions
    """

    wait_time = between(1, 3)  # Wait 1-3 seconds between requests
    host = "http://localhost:8000"

    # User credentials (generated on start)
    username = None
    email = None
    password = "LoadTest123!"
    jwt_token = None
    access_token = None

    def on_start(self):
        """
        Called when a simulated user starts

        Registers a new user, logs in, and tops up balance.
        Each virtual user gets unique credentials.
        """
        # Generate unique credentials
        self.username = f"loadtest_{secrets.token_hex(8)}"
        self.email = f"{self.username}@loadtest.local"

        logger.info(f"Starting user: {self.username}")

        # Register
        self.register()

        # Login
        self.login()

        # Top up balance (mock purchase)
        self.top_up_balance()

    def register(self):
        """Register a new user account"""
        with self.client.post(
            "/api/v1/auth/register",
            json={
                "email": self.email,
                "username": self.username,
                "password": self.password,
                "full_name": f"Load Test User {self.username}",
            },
            catch_response=True,
            name="/api/v1/auth/register",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Registration failed: {response.text}")

    def login(self):
        """Login and obtain JWT token"""
        with self.client.post(
            "/api/v1/auth/login",
            json={
                "email": self.email,
                "password": self.password,
            },
            catch_response=True,
            name="/api/v1/auth/login",
        ) as response:
            if response.status_code == 200:
                data = response.json()
                self.jwt_token = data.get("access_token")
                response.success()
            else:
                response.failure(f"Login failed: {response.text}")

    def top_up_balance(self, amount: int = 500):
        """
        Top up ZNC balance (mock purchase)

        Args:
            amount: ZNC amount to add (default: 500 ZNC = enough for ~17 hours)
        """
        with self.client.post(
            "/api/v1/currency/mock-purchase",
            json={"amount": amount},
            headers={"Authorization": f"Bearer {self.jwt_token}"},
            catch_response=True,
            name="/api/v1/currency/mock-purchase",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Balance top-up failed: {response.text}")

    @task(10)
    def get_balance(self):
        """Get current ZNC balance (most frequent operation)"""
        with self.client.get(
            "/api/v1/currency/balance",
            headers={"Authorization": f"Bearer {self.jwt_token}"},
            catch_response=True,
            name="/api/v1/currency/balance",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get balance failed: {response.text}")

    @task(8)
    def list_tokens(self):
        """List user's access tokens"""
        with self.client.get(
            "/api/v1/tokens/my-tokens?active_only=true",
            headers={"Authorization": f"Bearer {self.jwt_token}"},
            catch_response=True,
            name="/api/v1/tokens/my-tokens",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"List tokens failed: {response.text}")

    @task(3)
    def purchase_token(self):
        """
        Purchase a new access token

        Randomly selects duration (1h, 12h, or 24h).
        Tests balance deduction and token creation.
        """
        duration_hours = random.choice([1, 12, 24])  # Random duration

        with self.client.post(
            "/api/v1/tokens/purchase",
            json={
                "duration_hours": duration_hours,
                "scope": "full",
            },
            headers={"Authorization": f"Bearer {self.jwt_token}"},
            catch_response=True,
            name=f"/api/v1/tokens/purchase (duration={duration_hours}h)",
        ) as response:
            if response.status_code == 200:
                data = response.json()
                # Save token for proxy testing
                if not self.access_token:
                    self.access_token = data.get("token")
                response.success()
            elif response.status_code == 402:
                # Insufficient balance (expected if user ran out of ZNC)
                response.success()  # Don't mark as failure
                # Top up balance again
                self.top_up_balance()
            else:
                response.failure(f"Token purchase failed: {response.text}")

    @task(5)
    def get_transactions(self):
        """Get transaction history (pagination test)"""
        with self.client.get(
            "/api/v1/currency/transactions?skip=0&limit=10",
            headers={"Authorization": f"Bearer {self.jwt_token}"},
            catch_response=True,
            name="/api/v1/currency/transactions",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Get transactions failed: {response.text}")

    @task(2)
    def health_check(self):
        """
        Health check endpoint (monitoring)

        Lightweight endpoint to test basic availability.
        """
        with self.client.get(
            "/health",
            catch_response=True,
            name="/health",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Health check failed: {response.text}")

    @task(1)
    def metrics_check(self):
        """
        Prometheus metrics endpoint

        Tests metrics exposure (Phase 4 feature).
        """
        with self.client.get(
            "/metrics",
            catch_response=True,
            name="/metrics",
        ) as response:
            if response.status_code == 200:
                response.success()
            else:
                response.failure(f"Metrics endpoint failed: {response.text}")


class ProxyUser(HttpUser):
    """
    Simulates proxy usage (requires pre-existing access token)

    This user class focuses on proxy endpoint testing.
    Use ZenzefiUser to create tokens first, then use this class for proxy load testing.

    Note: Requires X-Device-ID header for device conflict detection.
    """

    wait_time = between(0.5, 2)  # Faster requests for proxy
    host = "http://localhost:8000"

    # Pre-configured access token (set via environment or config)
    access_token = None
    device_id = None

    def on_start(self):
        """Initialize proxy user with token and device ID"""
        # In real scenario, get token from environment or pre-setup
        # For load testing, create token manually first
        self.access_token = self.environment.parsed_options.access_token if hasattr(
            self.environment.parsed_options, "access_token"
        ) else None
        self.device_id = f"loadtest_device_{secrets.token_hex(10)}"

        if not self.access_token:
            logger.warning("No access token provided for ProxyUser, skipping tasks")

    @task(10)
    def proxy_status(self):
        """Check proxy authentication status"""
        if not self.access_token:
            return

        with self.client.get(
            "/api/v1/proxy/status",
            headers={
                "X-Access-Token": self.access_token,
                "X-Device-ID": self.device_id,
            },
            catch_response=True,
            name="/api/v1/proxy/status",
        ) as response:
            if response.status_code == 200:
                response.success()
            elif response.status_code == 409:
                # Device conflict (expected in load testing with multiple devices)
                response.success()
            else:
                response.failure(f"Proxy status failed: {response.text}")


# ===== EVENTS =====
@events.init_command_line_parser.add_listener
def on_locust_init(parser, **kwargs):
    """Add custom command-line arguments"""
    parser.add_argument(
        "--access-token",
        type=str,
        default=None,
        help="Access token for ProxyUser testing",
    )


@events.test_start.add_listener
def on_test_start(environment, **kwargs):
    """Called when load test starts"""
    logger.info("=" * 60)
    logger.info("Zenzefi Load Test Starting")
    logger.info("=" * 60)
    logger.info(f"Host: {environment.host}")
    logger.info(f"Users: {environment.runner.target_user_count if hasattr(environment.runner, 'target_user_count') else 'N/A'}")


@events.test_stop.add_listener
def on_test_stop(environment, **kwargs):
    """Called when load test stops"""
    logger.info("=" * 60)
    logger.info("Zenzefi Load Test Completed")
    logger.info("=" * 60)

    # Print summary statistics
    stats = environment.stats
    logger.info(f"Total requests: {stats.total.num_requests}")
    logger.info(f"Total failures: {stats.total.num_failures}")
    logger.info(f"Median response time: {stats.total.median_response_time}ms")
    logger.info(f"95th percentile: {stats.total.get_response_time_percentile(0.95)}ms")
    logger.info(f"Requests/second: {stats.total.total_rps:.2f}")
