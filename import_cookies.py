#!/usr/bin/env python3
"""
Importa cookies do seu navegador para o perfil do Playwright.

Uso:
  1. Exporte os cookies do Chrome/Firefox usando extensão (Cookie Editor, EditThisCookie)
  2. Salve em data/cookies.json
  3. python import_cookies.py

Isso faz o Google reconhecer o bot como "você" e evita verificações 2FA.
"""
import asyncio
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from playwright.async_api import async_playwright


async def import_cookies_to_profile():
    """Importa cookies do arquivo JSON para o perfil persistente."""
    cookies_file = Path.cwd() / "data" / "cookies.json"
    
    if not cookies_file.exists():
        print(f"❌ Arquivo {cookies_file} não encontrado!")
        print("\n📋 Passos:")
        print("  1. No Chrome, instale extensão 'Cookie Editor' ou 'EditThisCookie'")
        print("  2. Acesse https://admanager.google.com/23128820367")
        print("  3. Exporte os cookies como JSON")
        print("  4. Salve em data/cookies.json")
        print("  5. Rode este script de novo")
        return False
    
    print(f"📂 Lendo cookies de {cookies_file}")
    with open(cookies_file, "r") as f:
        cookies = json.load(f)
    
    print(f"✅ {len(cookies)} cookies carregados")
    
    # Converter formato de extensão para formato Playwright
    playwright_cookies = []
    for cookie in cookies:
        # Mapear sameSite para valores aceitos pelo Playwright
        same_site = cookie.get("sameSite", "Lax")
        if same_site in ["unspecified", "no_restriction", None, ""]:
            same_site = "None" if cookie.get("secure", False) else "Lax"
        else:
            same_site = same_site.capitalize()
        
        # Garantir que seja um dos valores aceitos
        if same_site not in ["Strict", "Lax", "None"]:
            same_site = "Lax"
        
        pw_cookie = {
            "name": cookie["name"],
            "value": cookie["value"],
            "domain": cookie["domain"],
            "path": cookie["path"],
            "expires": cookie.get("expirationDate", -1),
            "httpOnly": cookie.get("httpOnly", False),
            "secure": cookie.get("secure", False),
            "sameSite": same_site
        }
        playwright_cookies.append(pw_cookie)
    
    print("🚀 Iniciando Playwright e injetando cookies no perfil...")
    user_data_dir = Path.cwd() / "data" / "demo-user-data"
    user_data_dir.mkdir(exist_ok=True, parents=True)
    
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
    
    # Adicionar cookies ao contexto
    await browser.add_cookies(playwright_cookies)
    print(f"✅ {len(playwright_cookies)} cookies injetados no perfil")
    
    # Testar se funcionou
    page = await browser.new_page()
    print("🔍 Testando acesso ao Ad Manager...")
    await page.goto("https://admanager.google.com/23128820367", timeout=60000)
    await page.wait_for_timeout(5000)
    
    final_url = page.url
    print(f"📍 URL final: {final_url[:80]}...")
    
    if "admanager.google.com" in final_url and "accounts.google.com" not in final_url:
        print("✅ SUCESSO! Cookies funcionaram, você está logado!")
        await page.screenshot(path=Path.cwd() / "data" / "import_success.png")
        print("📸 Screenshot salvo em data/import_success.png")
        success = True
    else:
        print("⚠️  Ainda redirecionou para accounts.google.com")
        print("   Os cookies podem estar expirados ou incompletos")
        await page.screenshot(path=Path.cwd() / "data" / "import_failed.png")
        success = False
    
    await browser.close()
    await pw.stop()
    
    return success


def main():
    print("=" * 60)
    print("IMPORTADOR DE COOKIES - Google Ad Manager")
    print("=" * 60)
    
    success = asyncio.run(import_cookies_to_profile())
    
    if success:
        print("\n" + "=" * 60)
        print("✅ Cookies importados com sucesso!")
        print("=" * 60)
        print("\nAgora você pode:")
        print("  1. Rodar: python check_login.py")
        print("     (deve mostrar 'já está logado')")
        print("  2. Usar o bot normalmente sem precisar de 2FA")
        print("\n💡 Os cookies ficam salvos em data/demo-user-data/")
        return 0
    else:
        print("\n" + "=" * 60)
        print("❌ Importação falhou")
        print("=" * 60)
        print("\n🔧 Possíveis soluções:")
        print("  1. Certifique-se de estar logado no Chrome")
        print("  2. Exporte os cookies DEPOIS de fazer login")
        print("  3. Use uma extensão confiável (Cookie Editor)")
        print("  4. Verifique se o JSON está correto")
        return 1


if __name__ == "__main__":
    sys.exit(main())
