# CLAUDE.md

Datalake na AWS para dados públicos do TSE (eleições). Stack: **S3**, **Lambda**, **EventBridge**.

## Arquitetura

- **EventBridge** (regra agendada ou evento) dispara a **Lambda**.
- **Lambda** baixa o ZIP do TSE (`https://cdn.tse.jus.br/estatistica/sead/odsele/<contexto>/<contexto>_<ano>.zip`), lê cada CSV de dentro do ZIP e envia ao **S3** sem extrair para disco.
- **S3** (bucket padrão `tse-datalake-eleicoes`) armazena os dados em camadas (`raw/` é a atual).

### Layout no S3

```
raw/<contexto>/<UF>/<ano>/<arquivo>.csv
```

`<UF>` é extraída do final do nome do arquivo (ex.: `detalhe_votacao_secao_2024_SP.csv` → `SP`).

## Estrutura do repositório

- `scripts/main.py` — handler Lambda genérico (`lambda_handler`), parametrizado pelo evento (`contexto` e `years`) e por variáveis de ambiente. É a versão a ser evoluída.
- `scripts/*.py` (`detalhe_votacao_secao`, `detalhe_votacao_munzona`, `votacao_candidato_munzona`, `votacao_partido_munzona`) — scripts por contexto, com URL/prefixo fixos e execução via `main()`. Tendem a ser substituídos pelo `main.py` parametrizado; evite duplicar lógica neles.
- `env-tse/` — virtualenv local (Windows). **Não editar, não commitar, ignorar em buscas.**

## Evento da Lambda (`main.py`)

```json
{ "contexto": "detalhe_votacao_secao", "years": [2022, 2024] }
```

| Campo | Uso |
|---|---|
| `contexto` | Dataset do TSE; define URL e prefixo S3 (`raw/<contexto>`) |
| `years` | Lista de anos de eleição, processados um por vez |

Os dois campos são obrigatórios (não há valor padrão).

## Variáveis de ambiente (Lambda)

| Variável | Padrão | Uso |
|---|---|---|
| `S3_BUCKET` | `tse-datalake-eleicoes` | Bucket de destino |
| `REGION_AWS` | `us-east-2` | Região (não usar `AWS_REGION`, é reservada pela Lambda) |

## Convenções

- Python, boto3 + requests. Código e logs em português; docstrings curtas.
- Download em streaming (chunks de 8 MB) para `tempfile.TemporaryFile`; upload com `upload_fileobj`, um CSV por vez.
- Atenção a limites da Lambda: `/tmp` (512 MB por padrão, configurável até 10 GB), timeout (máx. 15 min) e memória. ZIPs grandes podem exigir ajustes ou outra abordagem (ex.: Fargate/Step Functions).
- Falhas: logar com `logging.exception` e encerrar com `sys.exit(1)`; a falha em um ano interrompe os seguintes.
- Idempotência: reexecuções sobrescrevem as mesmas chaves S3 (chave determinística); manter assim.
- Nunca commitar credenciais; usar IAM role da Lambda com permissão mínima (`s3:PutObject` no prefixo `raw/`).

## Pontos de atenção conhecidos

- Os scripts por contexto usam `AWS_REGION` (padrão `us-east-1`) e `parts[-2]` para o ano; o `main.py` usa `REGION_AWS` (padrão `us-east-2`) e recebe os anos em `years`. Manter o `main.py` como referência.

## Comandos úteis (PowerShell)

```powershell
.\env-tse\Scripts\Activate.ps1
pip install boto3 requests
python -c "from scripts.main import lambda_handler; lambda_handler({'contexto': 'detalhe_votacao_secao', 'years': [2024]}, None)"
```
