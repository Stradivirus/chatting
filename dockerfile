FROM python:3.9

WORKDIR /code

COPY ./requirements.txt /code/requirements.txt

RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

COPY . /code

# static 디렉토리의 존재를 확인
RUN ls -la /code/static

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]