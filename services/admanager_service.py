"""
Serviço minimalista para login no Google Ad Manager.
Contém apenas login_only e métodos auxiliares.
"""
import base64
import logging
import os
from pathlib import Path
from typing import Any, Dict

from playwright.async_api import Page, async_playwright

from config.settings import Config

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)

# Tempo de espera para verificação no celular (segundos) - via env VERIFICATION_WAIT_SECONDS
VERIFICATION_WAIT_SECONDS = int(os.getenv("VERIFICATION_WAIT_SECONDS", "60"))


class AdManagerService:
    def __init__(self) -> None:
        self.config = Config
        self.max_retries = 5
        self.retry_delay = 10

    async def login_only(self, network: str, headless: bool = True) -> Dict[str, Any]:
        """Apenas realiza o login no Ad Manager."""
        logger.info("login_only | start | network=%s headless=%s", network, headless)
        try:
            pw = await async_playwright().start()
            user_data_dir = Path.cwd() / "data" / "demo-user-data"
            user_data_dir.mkdir(exist_ok=True, parents=True)
            logger.info("login_only | user_data_dir=%s (exists=%s)", user_data_dir.resolve(), user_data_dir.exists())

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
            logger.info("login_only | browser launched, page created")
            result = await self._login_with_retry(page, network, "demo")
            logger.info("login_only | _login_with_retry result: success=%s message=%s", result.get("success"), result.get("message"))

            if result.get("success"):
                logger.info("login_only | login success, waiting 8s for Chromium to persist session to disk...")
                await page.wait_for_timeout(8000)
                
                # Exportar cookies após login bem-sucedido (backup automático)
                try:
                    import json
                    from datetime import datetime
                    cookies = await browser.cookies()
                    google_cookies = [c for c in cookies if "google.com" in c.get("domain", "") or "admanager" in c.get("domain", "")]
                    
                    cookies_file = Path.cwd() / "data" / "cookies_latest.json"
                    export_cookies = []
                    for cookie in google_cookies:
                        export_cookie = {
                            "domain": cookie["domain"],
                            "expirationDate": cookie.get("expires", -1),
                            "hostOnly": not cookie["domain"].startswith("."),
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
                    
                    with open(cookies_file, "w") as f:
                        json.dump(export_cookies, f, indent=2)
                    logger.info("login_only | %d cookies exported to %s", len(export_cookies), cookies_file)
                except Exception as e:
                    logger.warning("login_only | failed to export cookies: %s", e)
                
                logger.info("login_only | wait done, closing browser")
            else:
                logger.info("login_only | login failed, closing browser")

            await browser.close()
            await pw.stop()
            logger.info("login_only | browser and playwright stopped, returning")
            return result
        except Exception as e:
            logger.error(f"Demo login error: {str(e)}")
            return {
                "data": None,
                "success": False,
                "message": f"Demo login error: {str(e)}",
            }

    async def _login_with_retry(self, page: Page, network: str, task_id: str) -> Dict[str, Any]:
        logger.info("_login_with_retry | start | max_retries=%s", self.max_retries)
        for attempt in range(self.max_retries):
            logger.info("_login_with_retry | attempt %s/%s", attempt + 1, self.max_retries)
            result = await self._login(page, network, task_id)
            if result["success"]:
                logger.info("_login_with_retry | success on attempt %s", attempt + 1)
                return result
            logger.error("_login_with_retry | attempt %s failed: %s", attempt + 1, result["message"])
            if attempt < self.max_retries - 1:
                logger.info("_login_with_retry | waiting %ss before retry", self.retry_delay)
                await page.wait_for_timeout(self.retry_delay * 1000)

        logger.error("_login_with_retry | all attempts exhausted")
        return {
            "data": None,
            "success": False,
            "message": f"Failed to login after {self.max_retries} attempts",
        }

    async def _login(self, page: Page, network: str, task_id: str) -> Dict[str, Any]:
        url = f"https://admanager.google.com/{network}"
        logger.info("_login | goto %s", url)
        try:
            await page.goto(url, timeout=60000)
            logger.info("_login | after goto url=%s", page.url)

            if "accounts.google.com" in page.url:
                logger.info("_login | redirect to accounts.google.com, doing email/password")
                try:
                    logger.info("_login | filling email")
                    await page.wait_for_selector("#identifierId", state="visible", timeout=30000)
                    await page.fill("#identifierId", self.config.GOOGLE_EMAIL)
                    await page.click("#identifierNext")
                    logger.info("_login | email submitted")
                except Exception as e:
                    logger.error("_login | email step failed: %s", e)
                    return {"data": None, "success": False, "message": f"Failed at email step: {str(e)}"}

                try:
                    logger.info("_login | filling password")
                    await page.wait_for_selector('input[name="Passwd"]', timeout=30000)
                    await page.fill('input[name="Passwd"]', self.config.GOOGLE_PASSWORD)
                    await page.click("#passwordNext")
                    logger.info("_login | password submitted")
                except Exception as e:
                    logger.error("_login | password step failed: %s", e)
                    return {"data": None, "success": False, "message": f"Failed at password step: {str(e)}"}

                logger.info("_login | waiting 10s after password, then verification step")
                await page.wait_for_timeout(10000)

                verification_result = await self._verify_verification_step(page, network)
                logger.info("_login | verification result: success=%s", verification_result.get("success"))
                if not verification_result["success"]:
                    return verification_result

                # Após passkey ainda estamos em accounts.google.com; esperar redirect para o Ad Manager
                logger.info("_login | waiting for redirect to admanager.google.com (timeout 45s)")
                try:
                    await page.wait_for_url("**admanager.google.com**", timeout=45000)
                    logger.info("_login | redirect to admanager done, url=%s", page.url)
                except Exception as e:
                    logger.error("_login | redirect to admanager failed: %s | current url=%s", e, page.url)
                    return {
                        "data": None,
                        "success": False,
                        "message": f"Did not redirect to Ad Manager after verification: {page.url}",
                    }

            current_url = page.url
            logger.info("_login | current_url=%s", current_url)
            if "admanager.google.com" not in current_url or network not in current_url:
                logger.error("_login | not on admanager or network missing in url")
                return {
                    "data": None,
                    "success": False,
                    "message": f"Login verification failed. Expected admanager with network '{network}', got: {current_url}",
                }

            logger.info("_login | on admanager with network, waiting for networkidle + 3s to persist session")
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
                logger.info("_login | networkidle reached")
            except Exception as e:
                logger.warning("_login | networkidle timeout or error: %s", e)
            await page.wait_for_timeout(3000)
            logger.info("_login | returning success")

            return {"data": None, "success": True, "message": "Login successful"}

        except Exception as e:
            logger.error(f"Login error: {str(e)}")
            data_dir = Path.cwd() / "data"
            data_dir.mkdir(exist_ok=True, parents=True)
            await page.screenshot(path=data_dir / "login.png")
            return {
                "data": None,
                "success": False,
                "message": f"Authentication error: {str(e)}",
            }

    async def _verify_verification_step(self, page: Page, network: str) -> Dict[str, Any]:
        logger.info("_verify_verification_step | start | url=%s", page.url)
        data_dir = Path.cwd() / "data"
        data_dir.mkdir(exist_ok=True, parents=True)

        # Screenshot da página de verificação para debug
        await page.screenshot(path=data_dir / "verification_page.png")
        logger.info("_verify_verification_step | screenshot saved to verification_page.png")

        # 0. Detecta número de verificação e loga no console
        try:
            # Procurar por elementos que contenham números grandes (2 dígitos)
            number_element = await page.query_selector("div[data-challengetype='12'], div[jsname], div[class*='number'], div[class*='challenge']")
            if number_element:
                text = await number_element.inner_text()
                # Procurar por número de 2 dígitos
                import re
                numbers = re.findall(r'\b\d{2}\b', text)
                if numbers:
                    verification_number = numbers[0]
                    print("\n" + "🔢" * 35)
                    print(f"   NÚMERO DE VERIFICAÇÃO DETECTADO: {verification_number}")
                    print("🔢" * 35 + "\n")
                    logger.info("VERIFICATION_NUMBER | number=%s", verification_number)
                    
                    # Salvar o número em arquivo também
                    with open(data_dir / "verification_number.txt", "w") as f:
                        f.write(f"Número de verificação: {verification_number}\n")
                        f.write(f"Timestamp: {__import__('datetime').datetime.now()}\n")
        except Exception as e:
            logger.warning("_verify_verification_step | failed to detect number: %s", e)
        
        # Tentar detectar número de forma mais agressiva procurando no HTML
        try:
            content = await page.content()
            # Procurar por números de 2 dígitos no HTML que não sejam códigos comuns
            import re
            # Procurar por padrões como "31" ou números grandes isolados
            html_numbers = re.findall(r'>\s*(\d{2})\s*<', content)
            if html_numbers:
                # Filtrar números comuns (00, 01, etc.) e pegar o primeiro "incomum"
                for num in html_numbers:
                    if int(num) > 10:  # Números > 10 são mais prováveis de serem o código
                        print("\n" + "=" * 70)
                        print(f"🔢 NÚMERO DE VERIFICAÇÃO (HTML): {num}")
                        print("=" * 70 + "\n")
                        logger.info("VERIFICATION_NUMBER_HTML | number=%s", num)
                        break
        except Exception as e:
            logger.warning("_verify_verification_step | failed to detect number from HTML: %s", e)

        # 0. Detecta "Use your passkey" na tela de 2-Step Verification e clica
        try:
            content = await page.content()
            # Salva o HTML para debug
            with open(data_dir / "verification_page.html", "w", encoding="utf-8") as f:
                f.write(content)
            logger.info("_verify_verification_step | HTML saved, checking for passkey keywords")
            
            passkey_keywords = ["Use your passkey", "Usar sua chave de acesso", "passkey", "chave de acesso"]
            found_keywords = [kw for kw in passkey_keywords if kw.lower() in content.lower()]
            logger.info("_verify_verification_step | found keywords: %s", found_keywords)
            
            if any(kw.lower() in content.lower() for kw in passkey_keywords):
                logger.info("_verify_verification_step | passkey keywords found, clicking")
                passkey_selector = page.get_by_text("Use your passkey", exact=True)
                count_en = await passkey_selector.count()
                logger.info("_verify_verification_step | 'Use your passkey' count: %d", count_en)
                
                if count_en == 0:
                    passkey_selector = page.get_by_text("Usar sua chave de acesso", exact=True)
                    count_pt = await passkey_selector.count()
                    logger.info("_verify_verification_step | 'Usar sua chave de acesso' count: %d", count_pt)
                
                if await passkey_selector.count() > 0:
                    await page.screenshot(path=data_dir / "verify_passkey_before.png")
                    print("\n" + "=" * 70)
                    print("2-STEP VERIFICATION - Clicando em 'Use your passkey'")
                    print("=" * 70)
                    print(">>> ACEITE NO SEU CELULAR AGORA! <<<")
                    print(f"Aguardando {VERIFICATION_WAIT_SECONDS}s para você aprovar o passkey no celular...")
                    print("=" * 70 + "\n")
                    logger.info("PASSKEY_STEP | clicking Use your passkey | waiting=%ds", VERIFICATION_WAIT_SECONDS)
                    await passkey_selector.first.click()
                    
                    # Esperar a página mudar (você aprovar no celular) OU timeout
                    logger.info("_verify_verification_step | waiting for passkey approval (page change or Continue button)")
                    try:
                        # Espera aparecer o botão Continue (sinal de que você aprovou) ou mudar de página
                        await page.wait_for_selector("button:has-text('Continue'), button:has-text('Continuar')", 
                                                     state="visible", 
                                                     timeout=VERIFICATION_WAIT_SECONDS * 1000)
                        logger.info("_verify_verification_step | Continue button appeared (passkey approved)")
                    except Exception:
                        logger.warning("_verify_verification_step | timeout waiting for Continue button, checking page state")
                    
                    await page.screenshot(path=data_dir / "verify_passkey_after.png")
                    logger.info("Passkey wait completed")
                    
                    # Agora sim, clicar no botão "Continue" se aparecer
                    try:
                        logger.info("_verify_verification_step | looking for Continue button")
                        continue_button = page.get_by_role("button", name="Continue")
                        if await continue_button.count() == 0:
                            continue_button = page.get_by_role("button", name="Continuar")
                        if await continue_button.count() > 0:
                            logger.info("_verify_verification_step | clicking Continue button")
                            await continue_button.first.click()
                            await page.wait_for_timeout(3000)
                            logger.info("_verify_verification_step | Continue clicked")
                        else:
                            logger.warning("_verify_verification_step | Continue button not found after wait")
                    except Exception as e:
                        logger.warning("_verify_verification_step | Continue button error: %s", e)
            else:
                logger.warning("_verify_verification_step | passkey selector count is 0, trying alternative methods")
                # Tentar clicar em qualquer botão/link que contenha "passkey"
                try:
                    all_buttons = await page.query_selector_all("button, a, div[role='button']")
                    logger.info("_verify_verification_step | found %d clickable elements", len(all_buttons))
                    for btn in all_buttons:
                        text = await btn.inner_text()
                        if "passkey" in text.lower() or "chave de acesso" in text.lower():
                            logger.info("_verify_verification_step | found passkey element with text: %s", text)
                            await btn.click()
                            await page.wait_for_timeout(VERIFICATION_WAIT_SECONDS * 1000)
                            await page.screenshot(path=data_dir / "verify_passkey_after.png")
                            logger.info("Passkey clicked via alternative method")
                            
                            # Tentar clicar Continue
                            try:
                                continue_button = page.get_by_role("button", name="Continue")
                                if await continue_button.count() == 0:
                                    continue_button = page.get_by_role("button", name="Continuar")
                                if await continue_button.count() > 0:
                                    logger.info("_verify_verification_step | clicking Continue button")
                                    await continue_button.first.click()
                                    await page.wait_for_timeout(3000)
                            except Exception as e2:
                                logger.warning("_verify_verification_step | Continue button error: %s", e2)
                            break
                except Exception as e:
                    logger.error("_verify_verification_step | alternative passkey click failed: %s", e)
        except Exception as e:
            logger.error(f"Error during passkey step: {str(e)}")

        # 1. Detecta "Selecione o número correspondente" (challenge 2FA no celular) - prioridade
        try:
            content = await page.content()
            challenge_keywords = [
                "número correspondente",
                "número que corresponde",
                "número que aparece",
                "Selecione o número",
                "Select the matching number",
                "Select the number",
                "escolha o número",
                "matching number",
            ]
            if any(kw.lower() in content.lower() for kw in challenge_keywords):
                screenshot_path = data_dir / "verification_challenge.png"
                await page.screenshot(path=screenshot_path)

                # Salva e loga o base64 para visualizar
                with open(screenshot_path, "rb") as f:
                    b64 = base64.b64encode(f.read()).decode("ascii")

                print("\n" + "=" * 70)
                print("VERIFICAÇÃO REQUERIDA - Complete no seu celular!")
                print("=" * 70)
                print(f"Screenshot salvo em: {screenshot_path.absolute()}")
                print("\nPara ver a imagem (cole no navegador):")
                print("data:image/png;base64," + b64[:200] + "...(truncado)")
                print("\nOu baixe o arquivo do servidor:")
                print(f"  scp root@SEU_SERVIDOR:{screenshot_path} ./")
                print("\nAguardando %d segundos para você completar no celular..." % VERIFICATION_WAIT_SECONDS)
                print("=" * 70 + "\n")
                logger.info(
                    "VERIFICATION_CHALLENGE | screenshot=%s | base64_len=%d | waiting=%ds",
                    screenshot_path,
                    len(b64),
                    VERIFICATION_WAIT_SECONDS,
                )
                # Loga o base64 completo para copiar (em arquivo separado para não poluir stdout)
                base64_file = data_dir / "verification_challenge_b64.txt"
                with open(base64_file, "w") as f:
                    f.write("data:image/png;base64," + b64)
                print(f"Base64 completo em: {base64_file} - abra no servidor e cole no browser")

                await page.wait_for_timeout(VERIFICATION_WAIT_SECONDS * 1000)

                # Nova screenshot após espera
                await page.screenshot(path=data_dir / "verification_after_wait.png")
                logger.info("Verification wait completed, checking page state...")
        except Exception as e:
            logger.error(f"Error during verification challenge: {str(e)}")

        # 2. Tenta botão Avançar (identifierNext) se não era challenge
        try:
            confirm_button = await page.wait_for_selector("button#identifierNext", state="visible", timeout=3000)
            if confirm_button:
                logger.info("Confirmation step detected. Clicking 'Avançar'...")
                await page.screenshot(path=data_dir / "verify.png")
                await confirm_button.click()
                await page.wait_for_timeout(5000)
        except Exception:
            pass

        logger.info("_verify_verification_step | done, returning passed")
        return {"data": None, "success": True, "message": "Verification step passed"}
