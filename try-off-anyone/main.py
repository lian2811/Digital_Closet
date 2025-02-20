import sys
import os
#sys.path.append(os.path.dirname(os.path.abspath(__file__)))
#sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "src")))
from src.test_vton import test_vton
from src.inference import test_image
import argparse
from fastapi import FastAPI, HTTPException, BackgroundTasks, Query
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.requests import Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import uvicorn
from pathlib import Path
import base64
from gradio_client import Client, handle_file
import shutil
import random
import subprocess
import json
import requests


Public_URL = 'https://b7b5-2600-1700-eb40-4e90-8501-afee-4549-1e81.ngrok-free.app'

client = Client("franciszzj/Leffa")

app = FastAPI()

MODEL = 'pose6.jpg'
directory = Path("data")

app.mount("/static", StaticFiles(directory="data"), name="static")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 允许的来源，可以改为 ["http://localhost:3000"]
    allow_methods=["*"],  # 允许的 HTTP 方法，例如 ["GET", "POST", "OPTIONS"]
    allow_headers=["*"],  # 允许的 HTTP 头
)


class InferenceRequest(BaseModel):
    images: list[str]

class TryOnRequest(BaseModel):
    ref_image_path: str 

class SaveImageRequest(BaseModel):
    result: dict
    selected_image_name: str


def terminal_args():
    parser = argparse.ArgumentParser(description="Simple example of a training script.")
    parser.add_argument("--test", action="store_true")
    parser.add_argument("--inference", action="store_true")
    return parser.parse_known_args()[0]


def main():
    args = terminal_args()
    if args.test:
        test_vton()
    elif args.inference:
        test_image()
        
def get_next_filename(directory: Path, base_name: str, extension: str) -> str:
    """
    在目錄中檢查是否有重複的文件名，並基於最高數字生成新的文件名。

    :param directory: 要檢查的目錄。
    :param base_name: 文件的基本名稱（不包括數字或擴展名）。
    :param extension: 文件的擴展名（例如 .webp）。
    :return: 新的文件名，例如 image_1.webp。
    """
    # 列出目錄中所有文件
    existing_files = [file.name for file in directory.iterdir() if file.is_file()]

    # 匹配文件名格式，例如 image_1.webp
    highest_number = 0
    for file_name in existing_files:
        if file_name.startswith(base_name) and file_name.endswith(extension):
            # 提取數字部分
            parts = file_name[len(base_name):-len(extension)].strip("_")
            if parts.isdigit():
                highest_number = max(highest_number, int(parts))

    # 新的文件名
    new_number = highest_number + 1
    new_file_name = f"{base_name}_{new_number}{extension}"
    return new_file_name

def run_ai_inference(url: str):
    """AI 任务（在后台运行）"""
    try:
        test_image(url)
    except Exception as e:
        print(f"❌ AI 任务失败: {e}")
        
        
@app.get("/")
async def hello():
    return {"message": "Hello, World!"}
                

@app.post("/inference")
async def run_inference(background_tasks: BackgroundTasks, request: InferenceRequest):
    """
    接收多個圖片 URL
    """
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)  # 確保資料夾存在

    for url in request.images:
        background_tasks.add_task(run_ai_inference, url)




@app.get("/inference", response_class=JSONResponse)
async def list_files():
    if not directory.exists():
        raise HTTPException(status_code=404, detail="Data directory not found")
    
    files = [file.name for file in directory.iterdir() if file.is_file() and (file.name.startswith("clo") and (file.suffix == ".png" or file.suffix == ".json"))]

    if not files:
        raise HTTPException(status_code=404, detail="No files found in the data directory")
    
    file_map = {}
    for file in files:
        base_name = Path(file).stem
        if base_name not in file_map:
            file_map[base_name] = {"png": None, "json": None}

        if file.endswith(".png"):
            file_map[base_name]["png"] = f"http://127.0.0.1:8000/static/{file}"
        elif file.endswith(".json"):
            with open(directory / file, 'r') as json_file:
                file_map[base_name]["json"] = json.load(json_file)
        
    return {"files": file_map}

@app.get("/model", response_class=JSONResponse)
async def model():
    
    image = f"http://127.0.0.1:8000/static/{MODEL}"
    return {"images": image}

@app.post("/tryon")
async def tryon(request: TryOnRequest):
    src_image_path = Path(f"data/{MODEL}")
    file_name = Path(request.ref_image_path).name
    ref_image_url = Path("data") / file_name
    
    if not src_image_path.exists():
        raise HTTPException(status_code=404, detail="Source image (model.png) not found")

        # 使用 Gradio 客戶端進行推理
    try:
        result = client.predict(
            src_image_path=handle_file(str(src_image_path)),  # 本地的 model.png
            ref_image_path=handle_file(str(ref_image_url)),       # 遠端的參考圖片
            ref_acceleration=False,
            step=30,
            scale=2.5,
            seed=42,
            vt_model_type="viton_hd",
            vt_garment_type="upper_body",
            vt_repaint=False,
            api_name="/leffa_predict_vt"
        )
        generated_file_path=Path(result[0])
        base_name = "image"
        extension = ".webp"
        new_file_name = get_next_filename(directory, base_name, extension)
        final_path = directory / new_file_name

        # 移動文件
        shutil.move(generated_file_path, final_path)
        return {"generated_image": f"http://127.0.0.1:8000/static/{new_file_name}"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during try-on process: {str(e)}")
    
@app.post("/pose")
async def pose(request: TryOnRequest):
    pose_number = random.randint(1, 10)
    src_image_path = Path(f"data/pose{pose_number}.jpg")
    file_name = Path(request.ref_image_path).name
    ref_image_url = Path("data") / file_name

    # 確保來源圖片存在
    if not src_image_path.exists():
        raise HTTPException(status_code=404, detail="Source image not found in data directory")

    # 使用 Gradio 客戶端進行推理
    try:
        client = Client("franciszzj/Leffa")
        result = client.predict(
                src_image_path=handle_file(str(src_image_path)),
                ref_image_path=handle_file(str(ref_image_url)),
                ref_acceleration=False,
                step=30,
                scale=2.5,
                seed=42,
                api_name="/leffa_predict_pt"
        )
        generated_file_path=Path(result[0])
        base_name = "poes_result"
        extension = ".webp"
        new_file_name = get_next_filename(directory, base_name, extension)
        final_path = directory / new_file_name

        # 移動文件
        shutil.move(generated_file_path, final_path)
        return {"generated_image": f"http://127.0.0.1:8000/static/{new_file_name}"}

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error during try-on process: {str(e)}")
    
@app.post("/save_json")
async def save_json(request: SaveImageRequest):
    """
    接收結果 JSON 和選擇的圖片名稱，保存結果為 JSON 文件
    """
    output_dir = Path("data")
    output_dir.mkdir(exist_ok=True)  # 確保資料夾存在

    # 保存結果為 JSON 文件
    json_path = output_dir / (Path(request.selected_image_name).stem + ".json")
    with open(json_path, 'w') as json_file:
        json.dump(request.result, json_file)

    return {"saved_image": f"http://127.0.0.1:8000/static/{json_path.name}"}
    
@app.get("/get_match", response_class=JSONResponse)
def get_match(url: str = Query(..., description="圖片網址")):
    try:
        node_dir = "node"
        # 執行 Node.js 腳本
        fixurl = Public_URL+'/static/'+url.split("/")[-1]
        output_file = "node_output.json"
        with open(output_file, "w") as outfile:
            subprocess.run(
                ["node", "index.js", fixurl],
                stdout=outfile,
                stderr=subprocess.PIPE,
                text=True,
                check=True,
                cwd=node_dir,
            )
        
        # 讀取輸出結果
        with open(output_file, "r") as infile:
            json_output = json.load(infile)
        
        return JSONResponse(content={"results": json_output})

    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Node.js 錯誤: {e.stderr}")
    

if __name__ == '__main__':
    uvicorn.run(app, host='0.0.0.0', port=8000)
