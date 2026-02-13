#!/usr/bin/env python3
"""
Verifica se o usuário já está logado no Ad Manager usando o cache em data/.

Abre o browser com o mesmo user-data-dir (data/demo-user-data), acessa
https://admanager.google.com/{network} e verifica se há redirecionamento
para accounts.google.com (não logado) ou se permanece no Ad Manager (logado).

Uso:
  python check_login.py                    # network 23128820367 (padrão)
  python check_login.py --network 1234567
  python check_login.py --visible          # abre o browser visível

Docker (com volume data montado):
  docker-compose run --rm demo-login python check_login.py
  docker-compose run --rm demo-login python check_login.py --network 23128820367
"""
import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from dotenv import load_dotenv

load_dotenv(override=True)

from playwright.async_api import async_playwright

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger("check_login")

DEFAULT_NETWORK = "23128820367"
URL_TEMPLATE = "https://admanager.google.com/{}"


async def check_logged_in(network: str, headless: bool = True) -> bool:
    """Usa o cache em data/demo-user-data e verifica se já está logado."""
    user_data_dir = Path.cwd() / "data" / "demo-user-data"
    user_data_dir.mkdir(exist_ok=True, parents=True)
    logger.info("check_logged_in | user_data_dir=%s", user_data_dir.resolve())

    url = URL_TEMPLATE.format(network)
    logger.info("check_logged_in | opening browser with persistent context")

    pw = await async_playwright().start()
    browser = await pw.chromium.launch_persistent_context(
        str(user_data_dir),
        headless=headless,
        ignore_https_errors=True,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--disable-dev-shm-usage",
            "--no-sandbox",
            "--disable-setuid-sandbox",
            "--disable-gpu",
        ],
        viewport={"width": 1540, "height": 800},
        user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    )
    page = await browser.new_page()
    logger.info("check_logged_in | page created, goto %s", url)

    try:
        await page.goto(url, timeout=60000, wait_until="domcontentloaded")
        logger.info("check_logged_in | after goto url=%s", page.url)
        # Espera redirects terminarem (Google pode checar sessão)
        try:
            await page.wait_for_load_state("networkidle", timeout=15000)
            logger.info("check_logged_in | networkidle reached")
        except Exception as e:
            logger.warning("check_logged_in | networkidle timeout: %s", e)
        await page.wait_for_timeout(5000)
        current_url = page.url
        logger.info("check_logged_in | final url=%s", current_url)
        await browser.close()
        await pw.stop()
        logger.info("check_logged_in | browser closed")

        # Se foi para accounts.google.com = não está logado
        if "accounts.google.com" in current_url:
            logger.info("check_logged_in | result=NOT_LOGGED_IN (accounts.google.com)")
            print(f"   (URL atual: {current_url[:80]}...)", file=sys.stderr)
            return False
        # Se está no admanager com o network na URL = logado
        if "admanager.google.com" in current_url and network in current_url:
            logger.info("check_logged_in | result=LOGGED_IN (admanager + network in url)")
            return True
        # admanager pode redirecionar para outra URL ainda dentro do produto
        if "admanager.google.com" in current_url:
            logger.info("check_logged_in | result=LOGGED_IN (admanager in url)")
            return True
        logger.warning("check_logged_in | result=NOT_LOGGED_IN (unexpected url)")
        print(f"   (URL inesperada: {current_url[:80]}...)", file=sys.stderr)
        return False
    except Exception as e:
        logger.exception("check_logged_in | error: %s", e)
        print(f"Erro ao verificar: {e}", file=sys.stderr)
        await browser.close()
        await pw.stop()
        return False


def main():
    parser = argparse.ArgumentParser(description="Verifica se já está logado no Ad Manager (usa cache em data/)")
    parser.add_argument("--network", type=str, default=DEFAULT_NETWORK, help="Network ID (default: 23128820367)")
    parser.add_argument("--visible", action="store_true", help="Abre o browser visível")
    args = parser.parse_args()

    print(f"Verificando login em {URL_TEMPLATE.format(args.network)} usando cache em data/ ...")
    logged_in = asyncio.run(check_logged_in(args.network, headless=not args.visible))

    if logged_in:
        print("✅ Usuário já está logado (cache válido).")
        return 0
    else:
        print("❌ Usuário não está logado. Rode demo_login.py para fazer login.")
        return 1


if __name__ == "__main__":
    sys.exit(main())
