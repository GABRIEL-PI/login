"""
Serviço para criar URLs no Google Ad Manager.
"""
import logging
from pathlib import Path
from typing import Any, Dict, TypedDict

from playwright.async_api import Page, async_playwright

from config.settings import Config

logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")
logger = logging.getLogger(__name__)


class URLData(TypedDict, total=False):
    """Estrutura de dados para criar uma URL"""
    url: str
    inventory_type: str  # "Display" ou "Vídeo in-stream"
    brand_type: str  # "Com marca" ou "semitransparente"
    id: str  # ID opcional para identificação


class CreateURLService:
    def __init__(self) -> None:
        self.config = Config

    async def create_url(
        self, network: str, url_data: URLData, headless: bool = True
    ) -> Dict[str, Any]:
        """
        Cria uma URL no Google Ad Manager.
        
        Args:
            network: Network ID do Ad Manager
            url_data: Dados da URL a ser criada
            headless: Se True, roda em modo headless
            
        Returns:
            Dict com success, message e data
        """
        logger.info("create_url | start | network=%s url=%s", network, url_data.get("url"))
        
        try:
            pw = await async_playwright().start()
            user_data_dir = Path.cwd() / "data" / "demo-user-data"
            user_data_dir.mkdir(exist_ok=True, parents=True)
            logger.info("create_url | user_data_dir=%s", user_data_dir.resolve())

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
            logger.info("create_url | browser launched, page created")

            result = await self._create_url_safe(page, network, url_data)
            
            await browser.close()
            await pw.stop()
            logger.info("create_url | browser closed, returning")
            return result

        except Exception as e:
            logger.error(f"create_url | error: {str(e)}")
            return {
                "data": None,
                "success": False,
                "message": f"Error creating URL: {str(e)}",
            }

    async def _create_url_safe(
        self, page: Page, network: str, data: URLData
    ) -> Dict[str, Any]:
        """Create URL with comprehensive error handling"""
        try:
            await self._close_dialogs(page)
            await self._close_dialogs_reverify(page)
            
            url = f"https://admanager.google.com/{network}#inventory/url/list"
            logger.info("_create_url_safe | goto %s", url)
            await page.goto(url, timeout=60000)

            current_url = page.url
            logger.info("_create_url_safe | current_url=%s", current_url)
            
            # Check if redirected to login page (session expired)
            if "accounts.google.com" in current_url:
                logger.error("_create_url_safe | redirected to login page, session expired")
                return {
                    "data": None,
                    "success": False,
                    "message": "Session expired. Please run 'python demo_login.py' or 'python import_cookies.py' first.",
                }
            
            if network not in current_url:
                return {
                    "data": None,
                    "success": False,
                    "message": f"Navigation failed. Could not reach URL list page for network: {network}",
                }

            logger.info("_create_url_safe | waiting 10s for page to load")
            await page.wait_for_timeout(10000)

            logger.info("_create_url_safe | clicking 'Novo URL' button")
            create_result = await self._click_new_url_button_safe(page)
            if not create_result["success"]:
                return create_result

            logger.info("_create_url_safe | waiting 5s for form to open")
            await page.wait_for_timeout(5000)

            logger.info("_create_url_safe | configuring URL")
            configure_result = await self._configure_url_safe(page, data)
            return configure_result

        except Exception as e:
            logger.error(f"Error creating URL: {str(e)}")
            
            try:
                data_dir = Path.cwd() / "data"
                data_dir.mkdir(exist_ok=True, parents=True)
                screenshot_path = data_dir / f"error_url_{data.get('id', 'unknown')}.png"
                await page.screenshot(path=str(screenshot_path))
                logger.error(f"Screenshot saved: {screenshot_path}")
            except Exception as ss_e:
                logger.error(f"Failed to capture screenshot: {ss_e}")
            
            return {
                "data": None,
                "success": False,
                "message": f"Failed to create URL: {str(e)}",
            }

    async def _close_dialogs(self, page: Page) -> None:
        """Close any open dialogs"""
        try:
            dialog_locator = page.get_by_role("dialog", name="Novo painel")
            if await dialog_locator.is_visible():
                await dialog_locator.get_by_label("Fechar", exact=True).click()
        except Exception:
            pass  # Dialog might not exist
        
    async def _close_dialogs_reverify(self, page: Page) -> None:
        """Close any open 'Novo painel' modals"""
        try:
            dialog_close_button = page.locator(
                "div.close-button-container material-button[aria-label='Fechar']"
            )
            if await dialog_close_button.is_visible():
                await dialog_close_button.click()
        except Exception:
            pass  # Modal might not exist

    async def _click_new_url_button_safe(self, page: Page) -> Dict[str, Any]:
        """Click the 'Novo URL' button with error handling"""
        try:
            await self.create_url_button(page)
            return {
                "data": None,
                "success": True,
                "message": "New URL button clicked successfully",
            }
        except Exception as e:
            logger.error(f"Error clicking new URL button: {str(e)}")
            return {
                "data": None,
                "success": False,
                "message": f"Failed to click new URL button: {str(e)}",
            }

    async def create_url_button(self, page: Page) -> None:
        """Click the 'Novo URL' button"""
        try:
            if not page or page.is_closed():
                raise Exception("Page is closed or invalid")

            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    # Strategy 1: Try by role with exact name
                    try:
                        button = page.get_by_role("button", name="Novo URL", exact=True)
                        await button.wait_for(state="visible", timeout=20000)
                        await button.click()
                        await page.wait_for_timeout(1000)
                        logger.info("create_url_button | clicked via strategy 1 (role exact)")
                        return
                    except Exception:
                        pass

                    # Strategy 2: Try material-button with text
                    try:
                        button = page.locator('material-button:has-text("Novo URL")')
                        await button.wait_for(state="visible", timeout=20000)
                        await button.click()
                        await page.wait_for_timeout(1000)
                        logger.info("create_url_button | clicked via strategy 2 (material-button)")
                        return
                    except Exception:
                        pass

                    # Strategy 3: Try button with partial text match
                    try:
                        button = page.get_by_role("button", name="Novo URL")
                        await button.wait_for(state="visible", timeout=20000)
                        await button.click()
                        await page.wait_for_timeout(1000)
                        logger.info("create_url_button | clicked via strategy 3 (role partial)")
                        return
                    except Exception:
                        pass

                    # Strategy 4: Use JavaScript to find and click
                    try:
                        await page.evaluate("""
                            const buttons = Array.from(document.querySelectorAll('button, material-button'));
                            const button = buttons.find(el => el.textContent && el.textContent.includes('Novo URL'));
                            if (button) {
                                button.click();
                            }
                        """)
                        await page.wait_for_timeout(1000)
                        logger.info("create_url_button | clicked via strategy 4 (javascript)")
                        return
                    except Exception:
                        pass

                    if attempt < max_attempts - 1:
                        logger.warning(f"create_url_button | attempt {attempt + 1} failed, retrying")
                        await page.wait_for_timeout(1000)
                        continue
                    else:
                        raise Exception(f"Could not find 'Novo URL' button after {max_attempts} attempts")

                except Exception as e:
                    if attempt < max_attempts - 1:
                        logger.warning(f"Attempt {attempt + 1} failed, retrying: {str(e)}")
                        continue
                    else:
                        raise

        except Exception as e:
            logger.error(f"Error in create_url_button: {str(e)}")
            raise

    async def _configure_url_safe(
        self, page: Page, data: URLData
    ) -> Dict[str, Any]:
        """Configure URL with error handling"""
        try:
            await self.configure_url(page, data)
            return {
                "data": {
                    "url": data.get("url", ""),
                    "inventory_type": data.get("inventory_type", ""),
                    "brand_type": data.get("brand_type", ""),
                },
                "success": True,
                "message": "URL created and saved successfully",
            }
        except Exception as e:
            logger.error(f"Error configuring URL: {str(e)}")
            return {
                "data": None,
                "success": False,
                "message": f"Failed to configure URL: {str(e)}",
            }

    async def configure_url(self, page: Page, data: URLData) -> None:
        """Configure the URL form"""
        try:
            # Set URL field
            logger.info("configure_url | setting URL field")
            await self._set_url_field(page, data.get("url", ""))
            
            # Set inventory type (Tipo de inventário)
            logger.info("configure_url | setting inventory type")
            await self._set_inventory_type(page, data.get("inventory_type", "Display"))
            
            # Set brand type (Tipo de marca)
            logger.info("configure_url | setting brand type")
            await self._set_brand_type(page, data.get("brand_type", "Com marca"))
            
            # Save the URL
            logger.info("configure_url | saving URL")
            await self._save_url(page)
            logger.info("configure_url | URL saved successfully")

        except Exception as e:
            logger.error(f"Error in configure_url: {str(e)}")
            raise

    async def _set_url_field(self, page: Page, url: str) -> None:
        """Set the URL field"""
        try:
            if not url:
                raise ValueError("URL cannot be empty")

            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    # Strategy 1: Try by role
                    try:
                        url_input = page.get_by_role("textbox", name="URL")
                        await url_input.wait_for(state="visible", timeout=10000)
                        await url_input.fill(url)
                        await page.wait_for_timeout(500)
                        logger.info("_set_url_field | filled via strategy 1 (role)")
                        return
                    except Exception:
                        pass

                    # Strategy 2: Try by aria-label
                    try:
                        url_input = page.locator('input[aria-label="URL"], input[aria-label*="URL"]')
                        await url_input.wait_for(state="visible", timeout=10000)
                        await url_input.fill(url)
                        await page.wait_for_timeout(500)
                        logger.info("_set_url_field | filled via strategy 2 (aria-label)")
                        return
                    except Exception:
                        pass

                    # Strategy 3: Try by placeholder
                    try:
                        url_input = page.locator('input[placeholder*="URL"], input[placeholder*="url"]')
                        await url_input.wait_for(state="visible", timeout=10000)
                        await url_input.fill(url)
                        await page.wait_for_timeout(500)
                        logger.info("_set_url_field | filled via strategy 3 (placeholder)")
                        return
                    except Exception:
                        pass

                    # Strategy 4: Try by type="url" or type="text" near URL label
                    try:
                        url_input = page.locator('input[type="url"], input[type="text"]').first
                        await url_input.wait_for(state="visible", timeout=10000)
                        await url_input.fill(url)
                        await page.wait_for_timeout(500)
                        logger.info("_set_url_field | filled via strategy 4 (type)")
                        return
                    except Exception:
                        pass

                    if attempt < max_attempts - 1:
                        logger.warning(f"_set_url_field | attempt {attempt + 1} failed, retrying")
                        await page.wait_for_timeout(1000)
                        continue
                    else:
                        raise Exception(f"Could not find URL input field after {max_attempts} attempts")

                except Exception as e:
                    if attempt < max_attempts - 1:
                        logger.warning(f"Attempt {attempt + 1} failed, retrying: {str(e)}")
                        continue
                    else:
                        raise

        except Exception as e:
            logger.error(f"Error in _set_url_field: {str(e)}")
            raise

    async def _set_inventory_type(self, page: Page, inventory_type: str) -> None:
        """Set the inventory type dropdown (Tipo de inventário)"""
        try:
            # Valid options: "Display" or "Vídeo in-stream"
            valid_types = ["Display", "Vídeo in-stream"]
            if inventory_type not in valid_types:
                raise ValueError(f"Invalid inventory type. Must be one of: {valid_types}")

            # Find and click the inventory type dropdown
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    # Strategy 1: Procurar dentro do dialog/slide dialog primeiro
                    try:
                        # Procurar o botão dentro do create-url-slidealog com aria-haspopup
                        dropdown = page.locator('create-url-slidealog button[aria-label="Tipo de inventário"][aria-haspopup="listbox"]')
                        await dropdown.wait_for(state="visible", timeout=10000)
                        await dropdown.click(force=True)
                        await page.wait_for_timeout(2000)
                        logger.info("_set_inventory_type | dropdown clicked via strategy 1")
                    except Exception:
                        # Strategy 2: Procurar por role button com aria-label dentro do dialog
                        try:
                            dropdown = page.locator('create-url-slidealog').get_by_role("button", name="Tipo de inventário")
                            await dropdown.wait_for(state="visible", timeout=10000)
                            await dropdown.click(force=True)
                            await page.wait_for_timeout(2000)
                            logger.info("_set_inventory_type | dropdown clicked via strategy 2")
                        except Exception:
                            # Strategy 3: Usar JavaScript para encontrar e clicar no elemento correto
                            clicked = await page.evaluate("""
                                (() => {
                                    const buttons = Array.from(document.querySelectorAll('button[aria-label*="Tipo de inventário"], [aria-label*="Tipo de inventário"][role="button"]'));
                                    const button = buttons.find(el => {
                                        const dialog = el.closest('create-url-slidealog');
                                        return dialog && (el.getAttribute('aria-haspopup') === 'listbox' || el.tagName === 'BUTTON');
                                    });
                                    if (button) {
                                        button.click();
                                        return true;
                                    }
                                    return false;
                                })();
                            """)
                            if not clicked:
                                raise Exception("Could not find dropdown button")
                            await page.wait_for_timeout(2000)
                            logger.info("_set_inventory_type | dropdown clicked via strategy 3 (javascript)")
                    
                    # Aguardar o dropdown abrir
                    await page.wait_for_timeout(1500)
                    
                    # Select the option from dropdown
                    option_selected = False
                    
                    # Strategy 1: Procurar por role option
                    try:
                        option = page.get_by_role("option", name=inventory_type)
                        await option.wait_for(state="visible", timeout=5000)
                        await option.click()
                        option_selected = True
                        logger.info("_set_inventory_type | option selected via strategy 1 (role)")
                    except Exception:
                        pass
                    
                    # Strategy 2: Usar JavaScript como fallback
                    if not option_selected:
                        clicked = await page.evaluate(f"""
                            (() => {{
                                const options = Array.from(document.querySelectorAll('[role="option"]'));
                                const option = options.find(el => {{
                                    const text = el.textContent || '';
                                    return text.includes('{inventory_type}') || text.trim() === '{inventory_type}';
                                }});
                                if (option) {{
                                    option.click();
                                    return true;
                                }}
                                return false;
                            }})();
                        """)
                        if clicked:
                            option_selected = True
                            logger.info("_set_inventory_type | option selected via strategy 2 (javascript)")
                    
                    if not option_selected:
                        raise Exception(f"Could not find option '{inventory_type}' in dropdown")
                    
                    await page.wait_for_timeout(1000)
                    return
                    
                except Exception as e:
                    if attempt < max_attempts - 1:
                        logger.warning(f"Attempt {attempt + 1} failed, retrying: {str(e)}")
                        await page.wait_for_timeout(2000)
                        continue
                    else:
                        raise

        except Exception as e:
            logger.error(f"Error in _set_inventory_type: {str(e)}")
            raise

    async def _set_brand_type(self, page: Page, brand_type: str) -> None:
        """Set the brand type (Tipo de marca)"""
        try:
            # Valid options: "Com marca" or "semitransparente"
            valid_types = ["Com marca", "semitransparente"]
            if brand_type not in valid_types:
                raise ValueError(f"Invalid brand type. Must be one of: {valid_types}")

            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    # Strategy 1: Try radio button
                    try:
                        radio_button = page.get_by_role("radio", name=brand_type)
                        await radio_button.wait_for(state="visible", timeout=10000)
                        await radio_button.click()
                        await page.wait_for_timeout(1000)
                        logger.info("_set_brand_type | selected via strategy 1 (radio)")
                        return
                    except Exception:
                        pass

                    # Strategy 2: Try material-radio with text
                    try:
                        material_radio = page.locator(f'material-radio:has-text("{brand_type}")')
                        await material_radio.wait_for(state="visible", timeout=10000)
                        await material_radio.click()
                        await page.wait_for_timeout(1000)
                        logger.info("_set_brand_type | selected via strategy 2 (material-radio)")
                        return
                    except Exception:
                        pass

                    # Strategy 3: Use JavaScript to find and click
                    try:
                        await page.evaluate(f"""
                            const options = Array.from(document.querySelectorAll('material-radio, input[type="radio"]'));
                            const option = options.find(el => el.textContent && el.textContent.includes('{brand_type}'));
                            if (option) {{
                                option.click();
                            }}
                        """)
                        await page.wait_for_timeout(1000)
                        logger.info("_set_brand_type | selected via strategy 3 (javascript)")
                        return
                    except Exception:
                        pass

                    if attempt < max_attempts - 1:
                        logger.warning(f"_set_brand_type | attempt {attempt + 1} failed, retrying")
                        await page.wait_for_timeout(1000)
                        continue
                    else:
                        raise Exception(f"Could not find brand type option '{brand_type}' after {max_attempts} attempts")

                except Exception as e:
                    if attempt < max_attempts - 1:
                        logger.warning(f"Attempt {attempt + 1} failed, retrying: {str(e)}")
                        continue
                    else:
                        raise

        except Exception as e:
            logger.error(f"Error in _set_brand_type: {str(e)}")
            raise

    async def _save_url(self, page: Page) -> None:
        """Save the URL"""
        try:
            max_attempts = 3
            for attempt in range(max_attempts):
                try:
                    # Strategy 1: Try by role
                    try:
                        save_button = page.get_by_role("button", name="Salvar")
                        await save_button.wait_for(state="visible", timeout=20000)
                        await save_button.click()
                        await page.wait_for_timeout(2000)
                        logger.info("_save_url | clicked via strategy 1 (role)")
                        break
                    except Exception:
                        pass

                    # Strategy 2: Try material-button with text
                    try:
                        save_button = page.locator('material-button:has-text("Salvar")')
                        await save_button.wait_for(state="visible", timeout=20000)
                        await save_button.click()
                        await page.wait_for_timeout(2000)
                        logger.info("_save_url | clicked via strategy 2 (material-button)")
                        break
                    except Exception:
                        pass

                    # Strategy 3: Use JavaScript to find and click
                    try:
                        await page.evaluate("""
                            const buttons = Array.from(document.querySelectorAll('button, material-button'));
                            const button = buttons.find(el => el.textContent && el.textContent.includes('Salvar'));
                            if (button) {
                                button.click();
                            }
                        """)
                        await page.wait_for_timeout(2000)
                        logger.info("_save_url | clicked via strategy 3 (javascript)")
                        break
                    except Exception:
                        pass

                    if attempt < max_attempts - 1:
                        logger.warning(f"_save_url | attempt {attempt + 1} failed, retrying")
                        await page.wait_for_timeout(1000)
                        continue
                    else:
                        raise Exception(f"Could not find 'Salvar' button after {max_attempts} attempts")

                except Exception as e:
                    if attempt < max_attempts - 1:
                        logger.warning(f"Attempt {attempt + 1} failed, retrying: {str(e)}")
                        continue
                    else:
                        raise

            # Wait for confirmation or dialog dismissal
            await page.wait_for_timeout(3000)
            
            # Try to dismiss any success dialog
            try:
                dismiss_selectors = [
                    "material-button.dismiss-button",
                    'button[aria-label*="Fechar"]',
                    'button:has-text("Fechar")',
                ]
                for selector in dismiss_selectors:
                    try:
                        dismiss_button = page.locator(selector)
                        if await dismiss_button.is_visible(timeout=5000):
                            await dismiss_button.click()
                            await page.wait_for_timeout(1000)
                            logger.info("_save_url | success dialog dismissed")
                            break
                    except Exception:
                        continue
            except Exception:
                pass  # Dialog might not exist

        except Exception as e:
            logger.error(f"Error in _save_url: {str(e)}")
            raise
