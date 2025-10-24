#!/usr/bin/env python3
"""
Clear all users and tokens from the database
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import get_db
from app.models.token import AccessToken
from app.models.user import User

def main():
    """Clear all users and tokens from database"""
    db = next(get_db())

    try:
        # Count before deletion
        token_count = db.query(AccessToken).count()
        user_count = db.query(User).count()

        print('=' * 50)
        print('DATABASE CLEANUP')
        print('=' * 50)
        print(f'\nBefore deletion:')
        print(f'  → Tokens: {token_count}')
        print(f'  → Users: {user_count}')

        if token_count == 0 and user_count == 0:
            print('\n✓ Database is already empty!')
            return

        # Ask for confirmation
        print(f'\n⚠️  This will delete ALL {token_count} tokens and {user_count} users!')
        response = input('Continue? (yes/no): ')

        if response.lower() not in ['yes', 'y']:
            print('✗ Cancelled by user')
            return

        print('\nDeleting...')

        # Delete all tokens first (foreign key constraint)
        deleted_tokens = db.query(AccessToken).delete()
        print(f'  ✓ Deleted {deleted_tokens} tokens')

        # Delete all users
        deleted_users = db.query(User).delete()
        print(f'  ✓ Deleted {deleted_users} users')

        # Commit changes
        db.commit()
        print('\n✓ Changes committed to database')

        # Verify deletion
        remaining_tokens = db.query(AccessToken).count()
        remaining_users = db.query(User).count()

        print(f'\nAfter deletion:')
        print(f'  → Tokens: {remaining_tokens}')
        print(f'  → Users: {remaining_users}')

        print('\n✓ Database cleanup completed successfully!')

    except Exception as e:
        db.rollback()
        print(f'\n✗ Error during cleanup: {e}')
        raise
    finally:
        db.close()

if __name__ == '__main__':
    main()
