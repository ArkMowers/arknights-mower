# arknights-mower


### 镜像构建

```bash
docker build -t mower .
```

### 启动容器

```bash
docker run -d \
    --name mower\
    --network host \
    -e TZ="Asia/Shanghai" \
    --restart always \
    --memory 2g \
    mower
```


