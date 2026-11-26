# Como criar uma Layer para a Lambda

Este guia ensina a empacotar dependências (ex.: `requests`) em uma **Lambda Layer** e anexá-la à função que baixa os dados do TSE.

> Observação: o runtime Python da Lambda já inclui `boto3`, então **não é necessário** colocá-lo na layer. O `requests` não é garantido nos runtimes mais recentes, por isso é o principal candidato.

## 1. Pré-requisitos

- AWS CLI configurado (`aws configure`) com permissão para `lambda:PublishLayerVersion` e `lambda:UpdateFunctionConfiguration`.
- Python local na **mesma versão minor** do runtime da Lambda (ex.: Python 3.12). Confira o runtime da função no console.
- Região da layer **igual** à da função (neste projeto, `us-east-2`).

## 2. Estrutura obrigatória

O ZIP precisa ter a pasta `python/` na raiz. A Lambda só encontra pacotes nesse caminho.

```
layer.zip
└── python/
    ├── requests/
    ├── urllib3/
    ├── certifi/
    └── ...
```

## 3. Criar a pasta de build (PowerShell)

Faça fora da pasta `scripts/` e fora do `env-tse/`, por exemplo em `build/layer`:

```powershell
New-Item -ItemType Directory -Force build\layer\python | Out-Null
```

## 4. Instalar as dependências dentro de `python/`

Use as flags de plataforma para baixar binários compatíveis com o Linux da Lambda, mesmo estando no Windows:

```powershell
pip install requests `
  --target build\layer\python `
  --platform manylinux2014_x86_64 `
  --implementation cp `
  --python-version 3.12 `
  --only-binary=:all: `
  --upgrade
```

- Ajuste `--python-version` para o runtime da sua função.
- Se a função usar arquitetura **arm64**, troque para `--platform manylinux2014_aarch64`.
- `requests` é Python puro, mas as flags evitam problemas se você adicionar libs com código nativo (ex.: `pandas`, `pyarrow`).

Opcional, para reduzir o tamanho:

```powershell
Get-ChildItem build\layer\python -Recurse -Directory -Filter __pycache__ | Remove-Item -Recurse -Force
Get-ChildItem build\layer\python -Directory -Filter *.dist-info | Remove-Item -Recurse -Force
```

## 5. Gerar o ZIP

Use o módulo `zipfile` do Python, que grava caminhos com `/` (compatível com a Lambda):

```powershell
cd build\layer
python -m zipfile -c ..\requests-layer.zip python
cd ..\..
```

Confira o conteúdo:

```powershell
python -m zipfile -l build\requests-layer.zip | Select-Object -First 10
```

A primeira entrada deve começar com `python/`.

## 6. Publicar a layer

Limites: 50 MB zipado para upload direto; 250 MB descompactado somando função + todas as layers.

**Upload direto (ZIP até 50 MB):**

```powershell
aws lambda publish-layer-version `
  --layer-name tse-requests `
  --description "requests para download dos dados do TSE" `
  --zip-file fileb://build/requests-layer.zip `
  --compatible-runtimes python3.12 `
  --compatible-architectures x86_64 `
  --region us-east-2
```

**ZIP maior, via S3:**

```powershell
aws s3 cp build\requests-layer.zip s3://tse-datalake-eleicoes/layers/requests-layer.zip
aws lambda publish-layer-version `
  --layer-name tse-requests `
  --content S3Bucket=tse-datalake-eleicoes,S3Key=layers/requests-layer.zip `
  --compatible-runtimes python3.12 `
  --region us-east-2
```

A saída traz o `LayerVersionArn`, no formato:

```
arn:aws:lambda:us-east-2:<ACCOUNT_ID>:layer:tse-requests:1
```

## 7. Anexar à função Lambda

```powershell
aws lambda update-function-configuration `
  --function-name <NOME_DA_FUNCAO> `
  --layers arn:aws:lambda:us-east-2:<ACCOUNT_ID>:layer:tse-requests:1 `
  --region us-east-2
```

Atenção: `--layers` **substitui** a lista inteira. Se a função já tem outras layers, inclua todas os ARNs separados por espaço.

Pelo console: *Lambda → sua função → Layers → Add a layer → Custom layers*.

## 8. Testar

Invoque a função (console ou CLI) e verifique nos logs do CloudWatch que não há `ModuleNotFoundError: No module named 'requests'`.

## 9. Atualizar a layer

Layers são imutáveis: cada `publish-layer-version` cria uma **nova versão** (`:2`, `:3`...). Depois de publicar, rode novamente o passo 7 com o novo ARN. Versões antigas continuam existindo até serem apagadas:

```powershell
aws lambda delete-layer-version --layer-name tse-requests --version-number 1
```

## Problemas comuns

| Sintoma | Causa provável |
|---|---|
| `No module named 'requests'` | ZIP sem a pasta `python/` na raiz, ou layer não anexada |
| `cannot import name ... / invalid ELF header` | Dependência compilada para Windows; refaça com `--platform manylinux2014_*` |
| Erro de runtime incompatível | `--python-version` ou `--compatible-runtimes` diferentes do runtime da função |
| `Unzipped size must be smaller than 262144000 bytes` | Função + layers passam de 250 MB; remova dependências desnecessárias |

## Dica

Não commite `build/`. Adicione ao `.gitignore`:

```
build/
```
