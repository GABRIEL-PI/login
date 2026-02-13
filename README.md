# Demo Ad Manager Login

Projeto mínimo para testar o login no Google Ad Manager via Playwright em produção (Docker).

## Uso com Docker Compose

```bash
# 1. Copiar o env.example para .env e configurar credenciais
cp env.example .env
# Edite .env e preencha GOOGLE_EMAIL, GOOGLE_PASSWORD, ADMANAGER_NETWORK

# 2. Subir e executar
docker-compose run --rm demo-login

# Com network específico
ADMANAGER_NETWORK=123456789 docker-compose run --rm demo-login
```

## Uso local (sem Docker)

```bash
pip install -r requirements.txt
playwright install chromium
cp env.example .env
# Edite .env
python demo_login.py --network 23128820367
```

## Arquivos

- `demo_login.py` - Script principal
- `config/settings.py` - Configuração (email, senha)
- `services/admanager_service.py` - Serviço de login
- `data/` - Screenshots e user-data (montado em volume)
