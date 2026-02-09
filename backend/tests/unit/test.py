import time
import json
import httpx


def gen_image_test(
    prompt: str,
    api_key: str,
    base_url: str = "https://grsai.dakka.com.cn",
    model: str = "nano-banana-fast",
    image_size: str = "1K",
    aspect_ratio: str = "1:1",
    out_path: str = "out.png",
    timeout_sec: int = 60,
) -> str:
    submit_url = f"{base_url}/v1/draw/nano-banana"
    result_url = f"{base_url}/v1/draw/result"

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "prompt": prompt,
        "imageSize": image_size,
        "aspectRatio": aspect_ratio,
        "showProgress": True,
    }

    # 1) 提交任务（注意：这是 SSE，不是普通 JSON）
    with httpx.Client(timeout=60) as client:
        task_id = None

        with client.stream("POST", submit_url, headers=headers, json=payload) as resp:
            print("SUBMIT status:", resp.status_code, "ct:", resp.headers.get("content-type"))
            resp.raise_for_status()

            # 读取第一条 data: {...} 拿 id
            for line in resp.iter_lines():
                if not line:
                    continue
                if line.startswith("data:"):
                    line = line[len("data:"):].strip()

                # 有些实现会发 [DONE]
                if line == "[DONE]":
                    break

                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    # 可能是半行/非 JSON，跳过
                    continue

                task_id = obj.get("id") or (obj.get("data") or {}).get("id")
                print("SUBMIT first event:", obj)
                if task_id:
                    break

        if not task_id:
            raise RuntimeError("Submit did not return task id (SSE).")

        print("task_id:", task_id)

        # 2) 轮询结果（这里通常是标准 JSON）
        deadline = time.time() + timeout_sec
        while True:
            q = client.post(result_url, headers=headers, json={"id": task_id}, timeout=60)
            print("RESULT status:", q.status_code, "ct:", q.headers.get("content-type"))
            print("RESULT head:", q.text[:200])
            q.raise_for_status()

            jj = q.json()
            # 常见返回：{"code":0,"data":{...},"msg":"success"}
            if jj.get("code") not in (0, None):
                raise RuntimeError(f"Result error: {jj}")

            data = jj.get("data") or jj  # 有的平台直接返回 data 结构
            status = data.get("status")
            progress = data.get("progress", 0)
            print("status:", status, "progress:", progress)

            if status == "succeeded" or progress == 100:
                img_url = (data.get("results") or [])[0].get("url")
                if not img_url:
                    raise RuntimeError(f"No image url in result: {data}")

                img = client.get(img_url, timeout=180, follow_redirects=True)
                img.raise_for_status()
                with open(out_path, "wb") as f:
                    f.write(img.content)
                print("✅ OK saved:", out_path)
                return out_path

            if status in ("failed", "error"):
                raise RuntimeError(data.get("failure_reason") or data.get("error") or str(data))

            if time.time() > deadline:
                raise TimeoutError(f"Timed out. last data={data}")

            time.sleep(1)


def main():
    api_key = "sk-76af10b4030041fe9e90dfc519481883"
    if not api_key:
        raise SystemExit("请先设置环境变量 GRSAI_API_KEY")

    gen_image_test(
        prompt="一只戴墨镜的橘猫，赛博朋克街头，电影感",
        api_key=api_key,
        out_path="out.png",
        timeout_sec=60,
    )


if __name__ == "__main__":
    main()
