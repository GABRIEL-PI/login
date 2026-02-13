#!/usr/bin/env python3
"""
Script de demonstração do login no Google Ad Manager.
Usa dados mockados para exibir o fluxo de autenticação.

Uso:
  python demo_login.py                    # headless (padrão)
  python demo_login.py --visible          # abre o browser para você ver o login
  python demo_login.py --network 1234567  # network específico

Requer: GOOGLE_EMAIL e GOOGLE_PASSWORD no .env
"""
import asyncio
import argparse
import logging
import sys
from pathlib import Path

from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent))

load_dotenv(override=True)

from config.settings import Config
from services.admanager_service import AdManagerService

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("demo_login")

MOCK_NETWORK = "23128820367"


async def main():
    parser = argparse.ArgumentParser(description="Demo do login no Ad Manager")
    parser.add_argument("--visible", action="store_true", help="Abre o browser visível (headless=False)")
    parser.add_argument("--network", type=str, default=MOCK_NETWORK, help="Network ID do Ad Manager")
    args = parser.parse_args()

    logger.info("main | start | network=%s visible=%s", args.network, args.visible)
    print("=" * 50)
    print("DEMO: Login no Google Ad Manager")
    print("=" * 50)
    print(f"  Network: {args.network}")
    print(f"  Email:   {Config.GOOGLE_EMAIL or '(não configurado)'}")
    print(f"  Senha:   {'***' if Config.GOOGLE_PASSWORD else '(não configurado)'}")
    print(f"  Headless: {not args.visible}")
    print("=" * 50)

    if not Config.GOOGLE_EMAIL or not Config.GOOGLE_PASSWORD:
        logger.error("main | GOOGLE_EMAIL or GOOGLE_PASSWORD not set")
        print("\nERRO: Configure GOOGLE_EMAIL e GOOGLE_PASSWORD no .env")
        sys.exit(1)

    service = AdManagerService()
    logger.info("main | calling login_only")
    result = await service.login_only(args.network, headless=not args.visible)
    logger.info("main | login_only returned success=%s message=%s", result.get("success"), result.get("message"))

    print("\nResultado do login:")
    print(f"  Success: {result.get('success')}")
    print(f"  Message: {result.get('message')}")
    if result.get("success"):
        print("\n✅ Login concluído com sucesso!")
    else:
        print("\n❌ Login falhou.")
        print("   Screenshots em: data/login.png ou data/verify.png (se gerados)")

    return 0 if result.get("success") else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
