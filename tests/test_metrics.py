"""Integration tests for admin user metrics endpoints."""

from datetime import datetime, timezone
from uuid import uuid4

from fastapi.testclient import TestClient

from src.core.database import SessionLocal
from src.core.security import get_password_hash
from src.models.user import User
from src.repositories import metrics as metrics_repo


class TestUsersMetrics:
    METRICS_URL = "/users/admin/metrics/users"
    EXPORT_URL = "/users/admin/metrics/users/export"

    def _create_user(
        self,
        *,
        created_at: datetime,
        is_admin: bool = False,
        is_active: bool = True,
        email: str | None = None,
    ) -> User:
        with SessionLocal() as db:
            user = User(
                id=uuid4(),
                email=email or f"metrics-{uuid4().hex}@example.com",
                password=get_password_hash("Correct-P4ssw0rd!"),
                name="Metrics Test User",
                is_active=is_active,
                is_admin=is_admin,
                created_at=created_at,
            )
            db.add(user)
            db.commit()
            db.refresh(user)
            db.expunge(user)
            return user

    def _admin_headers(self, admin: User) -> dict[str, str]:
        return {"Authorization": f"Bearer token-for-{admin.id}"}

    def _baseline_total(self) -> int:
        with SessionLocal() as db:
            return metrics_repo.count_total_registered(db)

    def test_metrics_returns_200_for_admin(self, client: TestClient) -> None:
        admin = self._create_user(
            created_at=datetime(2018, 1, 1, tzinfo=timezone.utc),
            is_admin=True,
        )
        baseline = self._baseline_total()
        self._create_user(created_at=datetime(2018, 6, 1, 12, 0, tzinfo=timezone.utc))

        response = client.get(
            self.METRICS_URL,
            params={
                "start_date": "2018-06-01T00:00:00Z",
                "end_date": "2018-06-01T23:59:59Z",
            },
            headers=self._admin_headers(admin),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["total_registered_all_time"] == baseline + 1
        assert body["summary"]["new_users_in_period"] == 1
        assert body["timeseries"] == [{"date": "2018-06-01", "count": 1}]

    def test_metrics_excludes_admin_users_from_counts(self, client: TestClient) -> None:
        admin = self._create_user(
            created_at=datetime(2018, 2, 1, tzinfo=timezone.utc),
            is_admin=True,
        )
        baseline = self._baseline_total()
        self._create_user(created_at=datetime(2018, 7, 1, tzinfo=timezone.utc), is_admin=True)
        self._create_user(created_at=datetime(2018, 7, 2, tzinfo=timezone.utc))

        response = client.get(
            self.METRICS_URL,
            params={
                "start_date": "2018-07-01T00:00:00Z",
                "end_date": "2018-07-31T23:59:59Z",
            },
            headers=self._admin_headers(admin),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["total_registered_all_time"] == baseline + 1
        assert body["summary"]["new_users_in_period"] == 1

    def test_metrics_includes_blocked_users(self, client: TestClient) -> None:
        admin = self._create_user(
            created_at=datetime(2018, 3, 1, tzinfo=timezone.utc),
            is_admin=True,
        )
        baseline = self._baseline_total()
        self._create_user(
            created_at=datetime(2018, 8, 1, tzinfo=timezone.utc),
            is_active=False,
        )

        response = client.get(
            self.METRICS_URL,
            params={
                "start_date": "2018-08-01T00:00:00Z",
                "end_date": "2018-08-31T23:59:59Z",
            },
            headers=self._admin_headers(admin),
        )

        assert response.status_code == 200
        body = response.json()
        assert body["summary"]["total_registered_all_time"] == baseline + 1
        assert body["summary"]["new_users_in_period"] == 1

    def test_metrics_rejects_non_admin(self, client: TestClient) -> None:
        user = self._create_user(created_at=datetime(2018, 4, 1, tzinfo=timezone.utc))

        response = client.get(
            self.METRICS_URL,
            params={
                "start_date": "2018-04-01T00:00:00Z",
                "end_date": "2018-04-30T23:59:59Z",
            },
            headers=self._admin_headers(user),
        )

        assert response.status_code == 403
        assert response.json() == {"detail": "Admin access required"}

    def test_metrics_rejects_missing_token(self, client: TestClient) -> None:
        response = client.get(
            self.METRICS_URL,
            params={
                "start_date": "2018-05-01T00:00:00Z",
                "end_date": "2018-05-31T23:59:59Z",
            },
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Could not validate credentials"}

    def test_metrics_rejects_invalid_token(self, client: TestClient) -> None:
        response = client.get(
            self.METRICS_URL,
            params={
                "start_date": "2018-05-01T00:00:00Z",
                "end_date": "2018-05-31T23:59:59Z",
            },
            headers={"Authorization": "Bearer invalid-token"},
        )

        assert response.status_code == 401
        assert response.json() == {"detail": "Could not validate credentials"}

    def test_metrics_rejects_end_before_start(self, client: TestClient) -> None:
        admin = self._create_user(
            created_at=datetime(2018, 9, 1, tzinfo=timezone.utc),
            is_admin=True,
        )

        response = client.get(
            self.METRICS_URL,
            params={
                "start_date": "2018-10-02T00:00:00Z",
                "end_date": "2018-10-01T00:00:00Z",
            },
            headers=self._admin_headers(admin),
        )

        assert response.status_code == 422

    def test_metrics_rejects_range_over_six_months(self, client: TestClient) -> None:
        admin = self._create_user(
            created_at=datetime(2018, 10, 1, tzinfo=timezone.utc),
            is_admin=True,
        )

        response = client.get(
            self.METRICS_URL,
            params={
                "start_date": "2018-01-01T00:00:00Z",
                "end_date": "2018-07-02T00:00:00Z",
            },
            headers=self._admin_headers(admin),
        )

        assert response.status_code == 422

    def test_metrics_timeseries_day_buckets(self, client: TestClient) -> None:
        admin = self._create_user(
            created_at=datetime(2019, 1, 1, tzinfo=timezone.utc),
            is_admin=True,
        )
        self._create_user(created_at=datetime(2019, 3, 1, 10, 0, tzinfo=timezone.utc))
        self._create_user(created_at=datetime(2019, 3, 1, 18, 0, tzinfo=timezone.utc))
        self._create_user(created_at=datetime(2019, 3, 3, 12, 0, tzinfo=timezone.utc))

        response = client.get(
            self.METRICS_URL,
            params={
                "start_date": "2019-03-01T00:00:00Z",
                "end_date": "2019-03-03T23:59:59Z",
                "interval": "day",
            },
            headers=self._admin_headers(admin),
        )

        assert response.status_code == 200
        assert response.json()["timeseries"] == [
            {"date": "2019-03-01", "count": 2},
            {"date": "2019-03-02", "count": 0},
            {"date": "2019-03-03", "count": 1},
        ]

    def test_metrics_timeseries_week_interval(self, client: TestClient) -> None:
        admin = self._create_user(
            created_at=datetime(2019, 4, 1, tzinfo=timezone.utc),
            is_admin=True,
        )
        self._create_user(created_at=datetime(2019, 5, 6, 12, 0, tzinfo=timezone.utc))
        self._create_user(created_at=datetime(2019, 5, 8, 12, 0, tzinfo=timezone.utc))

        response = client.get(
            self.METRICS_URL,
            params={
                "start_date": "2019-05-06T00:00:00Z",
                "end_date": "2019-05-12T23:59:59Z",
                "interval": "week",
            },
            headers=self._admin_headers(admin),
        )

        assert response.status_code == 200
        assert response.json()["timeseries"] == [{"date": "2019-05-06", "count": 2}]

    def test_metrics_timeseries_month_interval(self, client: TestClient) -> None:
        admin = self._create_user(
            created_at=datetime(2019, 6, 1, tzinfo=timezone.utc),
            is_admin=True,
        )
        self._create_user(created_at=datetime(2019, 7, 10, tzinfo=timezone.utc))
        self._create_user(created_at=datetime(2019, 8, 15, tzinfo=timezone.utc))

        response = client.get(
            self.METRICS_URL,
            params={
                "start_date": "2019-07-01T00:00:00Z",
                "end_date": "2019-08-31T23:59:59Z",
                "interval": "month",
            },
            headers=self._admin_headers(admin),
        )

        assert response.status_code == 200
        assert response.json()["timeseries"] == [
            {"date": "2019-07-01", "count": 1},
            {"date": "2019-08-01", "count": 1},
        ]

    def test_export_returns_csv_with_summary_and_rows(self, client: TestClient) -> None:
        admin = self._create_user(
            created_at=datetime(2019, 9, 1, tzinfo=timezone.utc),
            is_admin=True,
        )
        self._create_user(created_at=datetime(2019, 10, 1, 12, 0, tzinfo=timezone.utc))
        self._create_user(created_at=datetime(2019, 10, 2, 12, 0, tzinfo=timezone.utc))

        response = client.get(
            self.EXPORT_URL,
            params={
                "start_date": "2019-10-01T00:00:00Z",
                "end_date": "2019-10-02T23:59:59Z",
            },
            headers=self._admin_headers(admin),
        )

        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert 'filename="users-metrics-2019-10-01-2019-10-02.csv"' in response.headers[
            "content-disposition"
        ]

        lines = response.text.splitlines()
        assert lines[0] == "metric,value"
        assert lines[1].startswith("total_registered_all_time,")
        assert lines[2] == "new_users_in_period,2"
        assert lines[3] == ""
        assert lines[4] == "date,new_users"
        assert lines[5] == "2019-10-01,1"
        assert lines[6] == "2019-10-02,1"

    def test_export_rejects_missing_dates(self, client: TestClient) -> None:
        admin = self._create_user(
            created_at=datetime(2019, 11, 1, tzinfo=timezone.utc),
            is_admin=True,
        )

        response = client.get(
            self.EXPORT_URL,
            params={"start_date": "2019-11-01T00:00:00Z"},
            headers=self._admin_headers(admin),
        )

        assert response.status_code == 422
