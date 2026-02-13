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

logging.basicConfig(level=logging.INFO)
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
        try:
            pw = await async_playwright().start()
            user_data_dir = Path.cwd() / "data" / "demo-user-data"
            user_data_dir.mkdir(exist_ok=True, parents=True)

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
            result = await self._login_with_retry(page, network, "demo")

            if result.get("success"):
                # Dá tempo do Chromium persistir cookies/sessão no disco antes de fechar
                await page.wait_for_timeout(3000)

            await browser.close()
            await pw.stop()
            return result
        except Exception as e:
            logger.error(f"Demo login error: {str(e)}")
            return {
                "data": None,
                "success": False,
                "message": f"Demo login error: {str(e)}",
            }

    async def _login_with_retry(self, page: Page, network: str, task_id: str) -> Dict[str, Any]:
        for attempt in range(self.max_retries):
            result = await self._login(page, network, task_id)
            if result["success"]:
                return result
            logger.error(f"Login attempt {attempt + 1} failed: {result['message']}")
            if attempt < self.max_retries - 1:
                await page.wait_for_timeout(self.retry_delay * 1000)

        return {
            "data": None,
            "success": False,
            "message": f"Failed to login after {self.max_retries} attempts",
        }

    async def _login(self, page: Page, network: str, task_id: str) -> Dict[str, Any]:
        try:
            await page.goto(f"https://admanager.google.com/{network}", timeout=60000)

            if "accounts.google.com" in page.url:
                try:
                    await page.wait_for_selector("#identifierId", state="visible", timeout=30000)
                    await page.fill("#identifierId", self.config.GOOGLE_EMAIL)
                    await page.click("#identifierNext")
                except Exception as e:
                    return {"data": None, "success": False, "message": f"Failed at email step: {str(e)}"}

                try:
                    await page.wait_for_selector('input[name="Passwd"]', timeout=30000)
                    await page.fill('input[name="Passwd"]', self.config.GOOGLE_PASSWORD)
                    await page.click("#passwordNext")
                except Exception as e:
                    return {"data": None, "success": False, "message": f"Failed at password step: {str(e)}"}

                await page.wait_for_timeout(10000)

                verification_result = await self._verify_verification_step(page, network)
                if not verification_result["success"]:
                    return verification_result

            current_url = page.url
            if network not in current_url:
                return {
                    "data": None,
                    "success": False,
                    "message": f"Login verification failed. Expected network '{network}' in URL, got: {current_url}",
                }

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
        data_dir = Path.cwd() / "data"
        data_dir.mkdir(exist_ok=True, parents=True)

        # 0. Detecta "Use your passkey" na tela de 2-Step Verification e clica
        try:
            content = await page.content()
            passkey_keywords = ["Use your passkey", "Usar sua chave de acesso", "passkey", "chave de acesso"]
            if any(kw.lower() in content.lower() for kw in passkey_keywords):
                passkey_selector = page.get_by_text("Use your passkey", exact=True)
                if await passkey_selector.count() == 0:
                    passkey_selector = page.get_by_text("Usar sua chave de acesso", exact=True)
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
                    await page.wait_for_timeout(VERIFICATION_WAIT_SECONDS * 1000)
                    await page.screenshot(path=data_dir / "verify_passkey_after.png")
                    logger.info("Passkey wait completed")
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

        return {"data": None, "success": True, "message": "Verification step passed"}
