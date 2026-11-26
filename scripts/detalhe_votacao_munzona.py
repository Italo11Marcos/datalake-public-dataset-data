
import logging
import os
import sys
import zipfile
import tempfile
from pathlib import PurePosixPath

import boto3
import requests
from botocore.exceptions import BotoCoreError, ClientError

URL = (
    "https://cdn.tse.jus.br/estatistica/sead/odsele/"
    "detalhe_votacao_munzona/detalhe_votacao_munzona_2024.zip"
)

S3_BUCKET = os.environ.get("S3_BUCKET", "tse-datalake-eleicoes")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
S3_PREFIX = "raw/detalhe_votacao_munzona"

CHUNK_SIZE = 8 * 1024 * 1024


def download_zip(temp_file):
    """Baixa o ZIP do TSE para um arquivo temporário."""
    logging.info("Iniciando download do TSE...")

    with requests.get(
        URL,
        stream=True,
        timeout=(30, 300),
    ) as response:
        response.raise_for_status()

        for chunk in response.iter_content(chunk_size=CHUNK_SIZE):
            if chunk:
                temp_file.write(chunk)

    temp_file.seek(0)
    logging.info("Download concluído.")


def get_path_from_filename(filename):
    """Extrai o caminho do arquivo a partir do nome."""

    parts = filename.split("_")
    uf = parts[-1].replace(".csv", "")
    s3_path = f"{S3_PREFIX}/{uf}/{parts[-2]}/{filename}"
    return s3_path

def upload_csv_files(temp_file):
    """Envia cada CSV contido no ZIP como um objeto separado no S3."""
    s3 = boto3.client("s3", region_name=AWS_REGION)

    uploaded = 0

    with zipfile.ZipFile(temp_file, "r") as zip_file:
        csv_files = [
            info
            for info in zip_file.infolist()
            if not info.is_dir()
            and PurePosixPath(info.filename).suffix.lower() == ".csv"
        ]

        if not csv_files:
            raise ValueError("Nenhum arquivo CSV foi encontrado no ZIP.")

        logging.info("Encontrados %s arquivos CSV.", len(csv_files))

        for info in csv_files:
            # Usa apenas o nome do arquivo, sem caminhos internos do ZIP.
            filename = PurePosixPath(info.filename).name
            s3_key = get_path_from_filename(filename)

            logging.info(
                "Enviando %s (%.2f MB)...",
                filename,
                info.file_size / (1024 * 1024),
            )

            # Lê um CSV por vez, sem extraí-lo para o disco.
            with zip_file.open(info, "r") as csv_file:
                s3.upload_fileobj(
                    csv_file,
                    S3_BUCKET,
                    s3_key,
                    ExtraArgs={"ContentType": "text/csv"},
                )

            uploaded += 1
            logging.info("Upload concluído: s3://%s/%s", S3_BUCKET, s3_key)

    logging.info("Processo concluído. Total de CSVs enviados: %s", uploaded)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    try:
        # O ZIP fica em memória até 64 MB; acima disso, vai para disco.
        with tempfile.TemporaryFile(mode="w+b") as temp_file:
            download_zip(temp_file)
            upload_csv_files(temp_file)

    except (
        requests.RequestException,
        zipfile.BadZipFile,
        ClientError,
        BotoCoreError,
        OSError,
        ValueError,
    ):
        logging.exception("Falha no processamento do arquivo do TSE.")
        sys.exit(1)


if __name__ == "__main__":
    main()