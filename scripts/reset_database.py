#!/usr/bin/env python3
"""
Reset database: drop all tables and apply migrations fresh
"""
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.database import engine
from sqlalchemy import text

def main():
    """Reset database completely"""
    print('=' * 50)
    print('DATABASE RESET')
    print('=' * 50)

    with engine.connect() as conn:
        # Get current database
        result = conn.execute(text("SELECT current_database();"))
        db_name = result.scalar()
        print(f'\nDatabase: {db_name}')

        # Get all tables
        result = conn.execute(text("""
            SELECT table_name
            FROM information_schema.tables
            WHERE table_schema = 'public'
            ORDER BY table_name;
        """))
        tables = [row[0] for row in result]

        print(f'\nFound {len(tables)} tables: {", ".join(tables)}')

        if len(tables) == 0:
            print('\nDatabase is already empty!')
            return

        # Confirm
        print(f'\nThis will DROP all tables!')
        response = input('Continue? (yes/no): ')

        if response.lower() not in ['yes', 'y']:
            print('Cancelled')
            return

        # Drop all tables
        print('\nDropping tables...')
        for table in tables:
            conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE;'))
            conn.commit()
            print(f'  - Dropped {table}')

        print('\nAll tables dropped successfully!')
        print('\nRun: poetry run alembic upgrade head')

if __name__ == '__main__':
    main()
