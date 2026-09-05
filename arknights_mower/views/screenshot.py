"""实时截图只读取内存快照，不等待写盘或扫描历史目录。"""

from flask import current_app, request


def _get_store():
    from arknights_mower.utils.log import screenshot_store

    return screenshot_store


def latest_screenshot_response():
    frame = _get_store().latest()
    if frame is None:
        response = current_app.response_class(status=204)
    else:
        etag = str(frame.captured_ns)
        unchanged = request.if_none_match.contains(etag)
        response = current_app.response_class(
            b"" if unchanged else frame.data,
            status=304 if unchanged else 200,
            mimetype="image/jpeg",
        )
        response.set_etag(etag)
    response.headers["Cache-Control"] = "no-store"
    # 开发环境的前后端可能跨域；客户端显式用 ETag 避免重复传输同一帧。
    response.headers["Access-Control-Expose-Headers"] = "ETag"
    return response
