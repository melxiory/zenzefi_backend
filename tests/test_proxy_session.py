"""
Tests for ProxySession tracking functionality
"""
import pytest
from datetime import datetime, timedelta, timezone
from uuid import uuid4

from app.models.proxy_session import ProxySession
from app.services.session_service import SessionService


class TestProxySessionModel:
    """Tests for ProxySession model"""

    def test_create_proxy_session(self, test_db, test_user, test_token):
        """Test creating a ProxySession"""
        session = ProxySession(
            user_id=test_user.id,
            token_id=test_token.id,
            ip_address="192.168.1.1",
            user_agent="Mozilla/5.0"
        )

        test_db.add(session)
        test_db.commit()
        test_db.refresh(session)

        assert session.id is not None
        assert session.user_id == test_user.id
        assert session.token_id == test_token.id
        assert session.ip_address == "192.168.1.1"
        assert session.user_agent == "Mozilla/5.0"
        assert session.request_count == 0
        assert session.bytes_transferred == 0
        assert session.is_active == True
        assert session.started_at is not None
        assert session.last_activity is not None
        assert session.ended_at is None

    def test_proxy_session_relationships(self, test_db, test_user, test_token):
        """Test ProxySession relationships with User and AccessToken"""
        session = ProxySession(
            user_id=test_user.id,
            token_id=test_token.id,
            ip_address="10.0.0.1"
        )

        test_db.add(session)
        test_db.commit()
        test_db.refresh(session)

        # Check relationships
        assert session.user.id == test_user.id
        assert session.user.username == test_user.username
        assert session.token.id == test_token.id
        assert session.token.token == test_token.token


class TestSessionService:
    """Tests for SessionService"""

    def test_track_request_creates_new_session(self, test_db, test_user, test_token):
        """Test that track_request creates a new session"""
        session = SessionService.track_request(
            user_id=test_user.id,
            token_id=test_token.id,
            ip_address="127.0.0.1",
            user_agent="Test Agent",
            bytes_transferred=1024,
            db=test_db
        )

        assert session.id is not None
        assert session.user_id == test_user.id
        assert session.token_id == test_token.id
        assert session.ip_address == "127.0.0.1"
        assert session.user_agent == "Test Agent"
        assert session.request_count == 1
        assert session.bytes_transferred == 1024
        assert session.is_active == True

    def test_track_request_updates_existing_session(self, test_db, test_user, test_token):
        """Test that track_request updates existing session"""
        # Create initial session
        session1 = SessionService.track_request(
            user_id=test_user.id,
            token_id=test_token.id,
            ip_address="127.0.0.1",
            user_agent="Test Agent",
            bytes_transferred=1024,
            db=test_db
        )

        initial_id = session1.id
        initial_time = session1.last_activity

        # Track another request (should update, not create)
        session2 = SessionService.track_request(
            user_id=test_user.id,
            token_id=test_token.id,
            ip_address="127.0.0.1",
            user_agent="Test Agent",
            bytes_transferred=2048,
            db=test_db
        )

        # Should be the same session
        assert session2.id == initial_id
        assert session2.request_count == 2
        assert session2.bytes_transferred == 3072  # 1024 + 2048
        assert session2.last_activity > initial_time

    def test_close_session(self, test_db, test_user, test_token):
        """Test closing an active session"""
        session = SessionService.track_request(
            user_id=test_user.id,
            token_id=test_token.id,
            ip_address="127.0.0.1",
            user_agent="Test Agent",
            db=test_db
        )

        # Close the session
        success = SessionService.close_session(session.id, test_db)

        assert success == True

        # Refresh session
        test_db.refresh(session)

        assert session.is_active == False
        assert session.ended_at is not None

    def test_close_nonexistent_session(self, test_db):
        """Test closing a non-existent session returns False"""
        fake_id = uuid4()
        success = SessionService.close_session(fake_id, test_db)

        assert success == False

    def test_cleanup_inactive_sessions(self, test_db, test_user, test_token):
        """Test cleanup of inactive sessions"""
        # Create an old session (2 hours ago)
        old_session = ProxySession(
            user_id=test_user.id,
            token_id=test_token.id,
            ip_address="192.168.1.1",
            last_activity=datetime.now(timezone.utc) - timedelta(hours=2)
        )
        test_db.add(old_session)

        # Create a recent session (30 minutes ago)
        recent_session = ProxySession(
            user_id=test_user.id,
            token_id=test_token.id,
            ip_address="192.168.1.2",
            last_activity=datetime.now(timezone.utc) - timedelta(minutes=30)
        )
        test_db.add(recent_session)

        test_db.commit()

        # Run cleanup (1 hour threshold)
        count = SessionService.cleanup_inactive_sessions(test_db, inactive_hours=1)

        assert count == 1  # Only old session should be closed

        # Check sessions
        test_db.refresh(old_session)
        test_db.refresh(recent_session)

        assert old_session.is_active == False
        assert old_session.ended_at is not None
        assert recent_session.is_active == True
        assert recent_session.ended_at is None

    def test_get_active_sessions(self, test_db, test_user, test_token, test_user_2, test_token_2):
        """Test getting active sessions"""
        # Create sessions for user 1
        session1 = SessionService.track_request(
            user_id=test_user.id,
            token_id=test_token.id,
            ip_address="127.0.0.1",
            user_agent="Agent 1",
            db=test_db
        )

        # Create session for user 2
        session2 = SessionService.track_request(
            user_id=test_user_2.id,
            token_id=test_token_2.id,
            ip_address="127.0.0.2",
            user_agent="Agent 2",
            db=test_db
        )

        # Get all active sessions
        all_sessions = SessionService.get_active_sessions(db=test_db)
        assert len(all_sessions) == 2

        # Get sessions for user 1 only
        user1_sessions = SessionService.get_active_sessions(user_id=test_user.id, db=test_db)
        assert len(user1_sessions) == 1
        assert user1_sessions[0].user_id == test_user.id

    def test_track_request_multiple_tokens_same_user(self, test_db, test_user, test_token, test_token_2):
        """Test tracking requests with different tokens for same user"""
        # Create session with token 1
        session1 = SessionService.track_request(
            user_id=test_user.id,
            token_id=test_token.id,
            ip_address="127.0.0.1",
            user_agent="Agent",
            db=test_db
        )

        # Assign token 2 to the same user
        test_token_2.user_id = test_user.id
        test_db.commit()

        # Create session with token 2
        session2 = SessionService.track_request(
            user_id=test_user.id,
            token_id=test_token_2.id,
            ip_address="127.0.0.1",
            user_agent="Agent",
            db=test_db
        )

        # Should create separate sessions (different tokens)
        assert session1.id != session2.id
        assert session1.token_id != session2.token_id

        # Both should be active
        sessions = SessionService.get_active_sessions(user_id=test_user.id, db=test_db)
        assert len(sessions) == 2
