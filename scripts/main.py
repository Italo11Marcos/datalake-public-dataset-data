
import logging
import json
import os
import sys
import zipfile
import tempfile
from pathlib import PurePosixPath

import boto3
import requests
from botocore.exceptions import BotoCoreError, ClientError

S3_BUCKET = os.environ.get("S3_BUCKET", "tse-datalake-eleicoes")
REGION_AWS = os.environ.get("REGION_AWS", "us-east-2")

CHUNK_SIZE = 8 * 1024 * 1024


def download_zip(temp_file, contexto, year):
    """Baixa o ZIP do TSE para um arquivo temporário."""
    logging.info("Iniciando download do TSE...")

    URL = (
        f"https://cdn.tse.jus.br/estatistica/sead/odsele/"
        f"{contexto}/{contexto}_{year}.zip"
    )

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


def get_path_from_filename(filename, year, s3_sufix):
    """Extrai o caminho do arquivo a partir do nome."""

    parts = filename.split("_")
    uf = parts[-1].replace(".csv", "")
    s3_path = f"{s3_sufix}/{uf}/{year}/{filename}"
    return s3_path

def upload_csv_files(temp_file, year, s3_sufix):
    """Envia cada CSV contido no ZIP como um objeto separado no S3."""
    s3 = boto3.client("s3", region_name=REGION_AWS)

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
            s3_key = get_path_from_filename(filename, year, s3_sufix)

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
            logging.info("Upload concluído: s3://%s/%s", s3_sufix, s3_key)

    logging.info("Processo concluído. Total de CSVs enviados: %s", uploaded)



def lambda_handler(event, context):

    logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s %(levelname)s %(message)s",
        )

    contexto = event.get("contexto")
    years = event.get("years")
    s3_sufix = f"raw/{contexto}"

    for year in years:
        try:
            # O ZIP fica em memória até 64 MB; acima disso, vai para disco.
            with tempfile.TemporaryFile(mode="w+b") as temp_file:
                download_zip(temp_file, contexto, year)
                upload_csv_files(temp_file, year, s3_sufix)

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

    return {
        'statusCode': 200,
        'body': json.dumps('Dados enviados ao S3 com sucesso')
    }