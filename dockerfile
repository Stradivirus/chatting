# Python 3.9 이미지를 기반으로 합니다.
FROM python:3.9

# 작업 디렉토리를 /code로 설정합니다.
WORKDIR /code

# requirements.txt 파일을 컨테이너의 /code 디렉토리로 복사합니다.
COPY ./requirements.txt /code/requirements.txt

# requirements.txt 파일에 명시된 패키지들을 설치합니다.
RUN pip install --no-cache-dir --upgrade -r /code/requirements.txt

# 현재 디렉토리의 모든 파일을 컨테이너의 /code 디렉토리로 복사합니다.
COPY . /code

# static 디렉토리의 존재를 확인합니다.
RUN ls -la /code/static

# MongoDB URI를 환경 변수로 설정합니다.
ENV MONGODB_URI=${MONGODB_URI}

# uvicorn을 사용하여 FastAPI 애플리케이션을 실행합니다.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]