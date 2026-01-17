#!/usr/bin/env python
"""
Secrets Management CLI
Command-line tool for managing secrets in the Local AI Hub

Usage:
    python secrets_cli.py set <key> <value>
    python secrets_cli.py get <key>
    python secrets_cli.py delete <key>
    python secrets_cli.py list
    python secrets_cli.py rotate <key>
    python secrets_cli.py status
    python secrets_cli.py import-env  # Import from .env file
"""
import sys
import os
import argparse
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from api.secrets_manager import (
    get_secrets_manager,
    SecretKeys,
    KEYRING_AVAILABLE,
    SECRETS_FILE
)


def cmd_set(args):
    """Set a secret value"""
    manager = get_secrets_manager()

    if args.value:
        value = args.value
    else:
        # Read from stdin for security
        import getpass
        value = getpass.getpass(f"Enter value for '{args.key}': ")

    manager.set(args.key, value)
    print(f"✓ Secret '{args.key}' stored successfully")


def cmd_get(args):
    """Get a secret value"""
    manager = get_secrets_manager()
    value = manager.get(args.key)

    if value:
        if args.show:
            print(value)
        else:
            # Show masked value
            masked = value[:4] + "*" * (len(value) - 8) + value[-4:] if len(value) > 8 else "*" * len(value)
            print(f"{args.key}: {masked}")
            print("(use --show to display full value)")
    else:
        print(f"✗ Secret '{args.key}' not found")
        sys.exit(1)


def cmd_delete(args):
    """Delete a secret"""
    manager = get_secrets_manager()

    if not args.force:
        confirm = input(f"Delete secret '{args.key}'? [y/N]: ")
        if confirm.lower() != 'y':
            print("Cancelled")
            return

    manager.delete(args.key)
    print(f"✓ Secret '{args.key}' deleted")


def cmd_list(args):
    """List all stored secrets"""
    manager = get_secrets_manager()
    keys = manager.list_keys()

    if not keys:
        print("No secrets stored")
        return

    print(f"Stored secrets ({len(keys)}):")
    print("-" * 40)
    for key in keys:
        print(f"  • {key}")


def cmd_rotate(args):
    """Rotate a secret value"""
    manager = get_secrets_manager()

    new_value = manager.rotate(args.key)
    if new_value:
        print(f"✓ Secret '{args.key}' rotated")
        if args.show:
            print(f"New value: {new_value}")
    else:
        print(f"✗ Secret '{args.key}' not found")
        sys.exit(1)


def cmd_status(args):
    """Show secrets storage status"""
    print("Secrets Storage Status")
    print("=" * 40)

    print("\nBackends:")
    print(f"  OS Credential Store: {'✓ Available' if KEYRING_AVAILABLE else '✗ Not available'}")
    print(f"  Encrypted File:      ✓ Available")
    print(f"    Path: {SECRETS_FILE}")
    print(f"  Environment Vars:    ✓ Available (LOCALAI_* prefix)")

    print("\nStandard Secret Keys:")
    for attr in dir(SecretKeys):
        if not attr.startswith('_'):
            key = getattr(SecretKeys, attr)
            manager = get_secrets_manager()
            exists = manager.get(key) is not None
            status = "✓" if exists else "○"
            print(f"  {status} {key}")


def cmd_import_env(args):
    """Import secrets from .env file"""
    env_file = args.file or Path(__file__).parent.parent / ".env"

    if not env_file.exists():
        print(f"✗ .env file not found: {env_file}")
        sys.exit(1)

    manager = get_secrets_manager()
    imported = 0

    with open(env_file, 'r') as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#'):
                continue

            if '=' not in line:
                continue

            key, value = line.split('=', 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            # Map common env vars to secret keys
            key_mapping = {
                "API_SECRET_KEY": SecretKeys.API_SECRET_KEY,
                "OPENAI_API_KEY": SecretKeys.OPENAI_API_KEY,
                "ANTHROPIC_API_KEY": SecretKeys.ANTHROPIC_API_KEY,
                "SLACK_WEBHOOK_URL": SecretKeys.SLACK_WEBHOOK_URL,
                "GITHUB_TOKEN": SecretKeys.GITHUB_TOKEN,
            }

            if key in key_mapping:
                secret_key = key_mapping[key]
                manager.set(secret_key, value)
                print(f"  ✓ Imported {key} → {secret_key}")
                imported += 1

    if imported:
        print(f"\n✓ Imported {imported} secrets")
        print("\nYou can now remove sensitive values from .env")
    else:
        print("No recognized secrets found in .env file")


def main():
    parser = argparse.ArgumentParser(
        description="Secrets Management CLI for Local AI Hub",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  secrets_cli.py set github_token ghp_xxxx    Set a secret
  secrets_cli.py set api_key                   Set interactively (hidden input)
  secrets_cli.py get github_token              Show masked value
  secrets_cli.py get github_token --show       Show full value
  secrets_cli.py list                          List all secrets
  secrets_cli.py rotate api_key                Generate new random value
  secrets_cli.py import-env                    Import from .env file
        """
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    # set
    p_set = subparsers.add_parser("set", help="Store a secret")
    p_set.add_argument("key", help="Secret key name")
    p_set.add_argument("value", nargs="?", help="Secret value (or enter interactively)")
    p_set.set_defaults(func=cmd_set)

    # get
    p_get = subparsers.add_parser("get", help="Retrieve a secret")
    p_get.add_argument("key", help="Secret key name")
    p_get.add_argument("--show", action="store_true", help="Show full value")
    p_get.set_defaults(func=cmd_get)

    # delete
    p_delete = subparsers.add_parser("delete", help="Delete a secret")
    p_delete.add_argument("key", help="Secret key name")
    p_delete.add_argument("-f", "--force", action="store_true", help="Skip confirmation")
    p_delete.set_defaults(func=cmd_delete)

    # list
    p_list = subparsers.add_parser("list", help="List stored secrets")
    p_list.set_defaults(func=cmd_list)

    # rotate
    p_rotate = subparsers.add_parser("rotate", help="Rotate a secret")
    p_rotate.add_argument("key", help="Secret key name")
    p_rotate.add_argument("--show", action="store_true", help="Show new value")
    p_rotate.set_defaults(func=cmd_rotate)

    # status
    p_status = subparsers.add_parser("status", help="Show storage status")
    p_status.set_defaults(func=cmd_status)

    # import-env
    p_import = subparsers.add_parser("import-env", help="Import from .env file")
    p_import.add_argument("--file", type=Path, help="Path to .env file")
    p_import.set_defaults(func=cmd_import_env)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
