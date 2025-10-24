#!/usr/bin/env python3
"""
Create separate test database (zenzefi_test)
"""
import psycopg2
from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

def main():
    """Create zenzefi_test database if it doesn't exist"""
    print('=' * 50)
    print('CREATE TEST DATABASE')
    print('=' * 50)

    # Connect to postgres default database
    conn = psycopg2.connect(
        host='localhost',
        user='zenzefi',
        password='devpassword',
        database='postgres'
    )
    conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)

    cursor = conn.cursor()

    try:
        # Check if database exists
        cursor.execute("SELECT 1 FROM pg_database WHERE datname = 'zenzefi_test';")
        exists = cursor.fetchone()

        if exists:
            print('\nDatabase "zenzefi_test" already exists')
        else:
            # Create database
            print('\nCreating database "zenzefi_test"...')
            cursor.execute('CREATE DATABASE zenzefi_test OWNER zenzefi;')
            print('[OK] Database "zenzefi_test" created successfully!')

        print('\n[OK] Test database is ready')
        print('\nDatabases:')
        print('  - zenzefi_dev  -> Development/Production')
        print('  - zenzefi_test -> Testing (isolated)')

    except Exception as e:
        print(f'\n[ERROR] Error: {e}')
        raise
    finally:
        cursor.close()
        conn.close()

if __name__ == '__main__':
    main()
