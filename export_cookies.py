#!/usr/bin/env python3
"""
Exporta os cookies do perfil do Playwright após login bem-sucedido.

Uso:
  python export_cookies.py

Salva em data/cookies_backup.json para você ter um backup atualizado.
"""
import asyncio
import json
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).parent))

from playwright.async_api import async_playwright


async def export_cookies_from_profile():
    """Exporta cookies do perfil persistente para arquivo JSON."""
    user_data_dir = Path.cwd() / "data" / "demo-user-data"
    
    if not user_data_dir.exists():
        print(f"❌ Perfil {user_data_dir} não existe!")
        print("   Rode demo_login.py primeiro para criar o perfil.")
        return False
    
    print(f"📂 Lendo cookies do perfil {user_data_dir}")
    
    pw = await async_playwright().start()
    browser = await pw.chromium.launch_persistent_context(
        str(user_data_dir),
        headless=True,
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
    
    # Pegar todos os cookies
    cookies = await browser.cookies()
    print(f"✅ {len(cookies)} cookies encontrados")
    
    # Filtrar apenas cookies do Google (relevantes)
    google_cookies = [c for c in cookies if "google.com" in c["domain"] or "admanager" in c["domain"]]
    print(f"🔍 {len(google_cookies)} cookies do Google")
    
    await browser.close()
    await pw.stop()
    
    # Salvar em formato compatível com extensões de navegador
    export_cookies = []
    for cookie in google_cookies:
        export_cookie = {
            "domain": cookie["domain"],
            "expirationDate": cookie.get("expires", -1),
            "hostOnly": cookie["domain"].startswith(".") == False,
            "httpOnly": cookie.get("httpOnly", False),
            "name": cookie["name"],
            "path": cookie["path"],
            "sameSite": cookie.get("sameSite", "unspecified").lower(),
            "secure": cookie.get("secure", False),
            "session": cookie.get("expires", -1) == -1,
            "storeId": "0",
            "value": cookie["value"],
        }
        export_cookies.append(export_cookie)
    
    # Salvar com timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_file = Path.cwd() / "data" / f"cookies_backup_{timestamp}.json"
    latest_file = Path.cwd() / "data" / "cookies_latest.json"
    
    with open(backup_file, "w") as f:
        json.dump(export_cookies, f, indent=2)
    
    with open(latest_file, "w") as f:
        json.dump(export_cookies, f, indent=2)
    
    print(f"💾 Cookies salvos em:")
    print(f"   - {backup_file}")
    print(f"   - {latest_file}")
    
    return True


def main():
    print("=" * 60)
    print("EXPORTADOR DE COOKIES - Google Ad Manager")
    print("=" * 60)
    
    success = asyncio.run(export_cookies_from_profile())
    
    if success:
        print("\n✅ Cookies exportados com sucesso!")
        print("\n💡 Use esses cookies para:")
        print("  - Backup (se o perfil corromper)")
        print("  - Importar em outro servidor")
        print("  - Compartilhar sessão entre ambientes")
        return 0
    else:
        return 1


if __name__ == "__main__":
    sys.exit(main())
