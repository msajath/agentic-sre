"""Local provisioning: python -m src.manage USERNAME --role SRE_LEAD."""
import argparse
import getpass
from src.database import init_db
from src.models.auth import UserRole
from src.services.auth_service import auth_service

def main():
    parser = argparse.ArgumentParser(description="Create or rotate an account using a hidden password prompt.")
    parser.add_argument("username")
    parser.add_argument("--role", choices=[r.value for r in UserRole], default="OPERATOR")
    args = parser.parse_args()
    password = getpass.getpass("Password (12-128 characters): ")
    if password != getpass.getpass("Confirm password: "):
        parser.error("Passwords do not match.")
    init_db()
    auth_service.provision_user(args.username, password, UserRole(args.role))
    print(f"Account {args.username} provisioned with role {args.role}.")

if __name__ == "__main__":
    main()
