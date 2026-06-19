  # 테스트 방법
  # 1. nginx 다운 테스트 방법
  ```
  was ec2 에 접속 후
  sudo systemctl stop nginx

  이후 시간 지나고 난 후 fastapi 에서 
  curl http://localhost:8001/aiops/last
  위 코드로 확인 가능
  ```

  # 2. 용량 95% 이상 사용
  ```
  was ec2 에 접속 후
  sudo fallocate -l 6G /dummy_fill

  df -h / <- 용량 확인 커맨드임 95%이상 차면 alert 조건이라 부족하면 더 채우기
  6G 부분이 용량임 부족하면 더 채우면됨

이후 시간 지나고 난 후 fastapi 에서 
  curl http://localhost:8001/aiops/last
  위 코드로 확인 가능
  ```
  # 3. 좀비프로세스
```
was ec2 접속 후 아래 커맨드 통째로 복사 후 붙여넣기
   python3 -c "
 import os, time
 pid = os.fork()
 if pid > 0:
     time.sleep(300)
 else:
     os._exit(0)
 " &

   이후 시간 지나고 난 후 fastapi 에서 
  curl http://localhost:8001/aiops/last
  위 코드로 확인 가능
```
# 4. 풀 다참
```
for i in $(seq 1 40); do
  docker exec -d postgres psql -U scott -d testdb -c "SELECT pg_sleep(300);"
done
db에 들어가서 입력


kill -9 $(ps aux | grep "pg_sleep" | grep -v grep | awk '{print $2}')
끄는법

현재 얼마나 풀이 찼는지 확인
docker exec postgres psql -U scott -d testdb -c "SELECT count(*) FROM pg_stat_activity;"

총 풀의 개수
docker exec postgres psql -U scott -d testdb -c "SHOW max_connections;"
```
# 5. db 프로세스 다운
```

  db ec2 들어가서
  docker stop postgres

  이후 시간 지나고 난 후 fastapi 에서 
  curl http://localhost:8001/aiops/last
  위 코드로 확인 가능

프로세스를 한 번 다운 시킨 다음에는 exporter와의 연결을 다시 해야함

docker stop postgres-exporter && docker rm postgres-exporter
위 코드 입력 후 아래 코드 통째로 입력

 docker run -d \
   --name postgres-exporter \
   --restart always \
   --network host \
   -e DATA_SOURCE_NAME="postgresql://scott:tiger@localhost:5432/testdb?sslmode=disable" \
   prometheuscommunity/postgres-exporter
 



 curl -s http://localhost:9187/metrics | grep pg_up
 이거 작성 시 pg_up 1 나오면 정상
```