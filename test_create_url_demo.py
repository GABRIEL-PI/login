#!/usr/bin/env python3
"""
Script de teste para criar uma URL no Google Ad Manager.

Uso:
  python test_create_url_demo.py                    # headless (padrão)
  python test_create_url_demo.py --visible          # abre o browser visível
  python test_create_url_demo.py --url example.com  # URL específica
"""
import asyncio
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(override=True)

from services.create_url_service import CreateURLService, URLData

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("test_create_url")

MOCK_NETWORK = "23128820367"


async def main():
    parser = argparse.ArgumentParser(description="Teste de criação de URL no Ad Manager")
    parser.add_argument("--visible", action="store_true", help="Abre o browser visível (headless=False)")
    parser.add_argument("--network", type=str, default=MOCK_NETWORK, help="Network ID do Ad Manager")
    parser.add_argument("--url", type=str, default="example.com", help="URL a ser criada")
    parser.add_argument("--inventory", type=str, default="Display", 
                        choices=["Display", "Vídeo in-stream"], 
                        help="Tipo de inventário")
    parser.add_argument("--brand", type=str, default="Com marca", 
                        choices=["Com marca", "semitransparente"], 
                        help="Tipo de marca")
    args = parser.parse_args()

    logger.info("main | start | network=%s url=%s", args.network, args.url)
    print("=" * 60)
    print("TESTE: Criar URL no Google Ad Manager")
    print("=" * 60)
    print(f"  Network:        {args.network}")
    print(f"  URL:            {args.url}")
    print(f"  Tipo inventário: {args.inventory}")
    print(f"  Tipo marca:     {args.brand}")
    print(f"  Headless:       {not args.visible}")
    print("=" * 60)

    url_data: URLData = {
        "url": args.url,
        "inventory_type": args.inventory,
        "brand_type": args.brand,
        "id": "test_demo",
    }

    service = CreateURLService()
    logger.info("main | calling create_url")
    result = await service.create_url(args.network, url_data, headless=not args.visible)
    logger.info("main | create_url returned success=%s message=%s", result.get("success"), result.get("message"))

    print("\nResultado:")
    print(f"  Success: {result.get('success')}")
    print(f"  Message: {result.get('message')}")
    
    if result.get("data"):
        print(f"  Data:")
        for key, value in result["data"].items():
            print(f"    {key}: {value}")
    
    if result.get("success"):
        print("\n✅ URL criada com sucesso!")
        print("\n💡 Verifique no Ad Manager:")
        print(f"   https://admanager.google.com/{args.network}#inventory/url/list")
        return 0
    else:
        print("\n❌ Falha ao criar URL.")
        print("   Screenshots de erro podem estar em: data/error_url_*.png")
        return 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
