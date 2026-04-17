import asyncio, json, re, os, csv
import pandas as pd
from playwright.async_api import async_playwright
from tqdm.asyncio import tqdm

# --- CẤU HÌNH ---
INPUT_FILE = "man_hinh_may_tinh_urls.csv" 
OUTPUT_FILE = "man_hinh_full_data.csv"
MAX_TABS = 1 # 🔴 ĐỂ 1 CHO ỔN ĐỊNH TUYỆT ĐỐI, KHÔNG BỊ PHONG VŨ CHẶN

async def scrape_one(context, url, sem, writer, f_handle):
    async with sem:
        page = await context.new_page()
        # Giả lập trình duyệt xịn
        await page.set_extra_http_headers({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36"
        })
        
        result = {
            "url": url, "product_name": "N/A", "current_price": 0, 
            "product_code": "N/A", "category": "Monitor", "specifications": "{}"
        }
        
        try:
            # Chờ trang tải ổn định
            await page.goto(url, wait_until="domcontentloaded", timeout=60000)
            await page.wait_for_timeout(2000) # Nghỉ chút cho ổn định
            
            # Lấy Tên & Giá (Thường cái này luôn có)
            try:
                result["product_name"] = (await page.locator("h1").inner_text()).strip()
                price_txt = await page.locator(".att-product-detail-latest-price").first.inner_text()
                result["current_price"] = int(re.sub(r"\D", "", price_txt))
                sku_full = await page.locator(".css-1f5a6jh").first.inner_text()
                result["product_code"] = sku_full.replace("SKU:", "").strip()
            except: pass

            # 🔴 CHIẾN THUẬT VÉT CẠN BẢNG THÔNG SỐ
            # Bước 1: Cuộn từ từ để "đánh thức" trang web
            for _ in range(3):
                await page.mouse.wheel(0, 500)
                await page.wait_for_timeout(800)

            # Bước 2: Thử click nút bằng JavaScript (Chấp cả banner che)
            await page.evaluate("""() => {
                const targets = ["Xem thông tin chi tiết", "Xem cấu hình chi tiết", "Thông số kỹ thuật"];
                const elements = Array.from(document.querySelectorAll('button, div, span, p'));
                const btn = elements.find(el => targets.some(t => el.textContent.includes(t)));
                if (btn) {
                    btn.scrollIntoView();
                    btn.click();
                }
            }""")
            
            # Bước 3: Đợi bảng xuất hiện (Retry 3 lần nếu chưa thấy)
            found_container = False
            for _ in range(3):
                try:
                    # Đợi cái container css-10u9x48 mà Bình đã thấy
                    await page.wait_for_selector('.css-10u9x48', timeout=5000)
                    found_container = True
                    break
                except:
                    # Nếu chưa thấy, thử click lại lần nữa bằng cách khác
                    btn_retry = page.get_by_text("Xem thông tin chi tiết", exact=False)
                    if await btn_retry.count() > 0:
                        await btn_retry.first.click(force=True)
                    await page.wait_for_timeout(2000)

            # Bước 4: Nếu thấy container thì bốc dữ liệu
            if found_container:
                product_specs = {}
                current_group = "Thông tin chung"
                # Lấy toàn bộ div con để quét
                elements = await page.locator(".css-10u9x48 > div").all()
                for el in elements:
                    cls = await el.get_attribute("class") or ""
                    text = (await el.inner_text()).strip()
                    if not text: continue
                    
                    if "css-1geo7k4" in cls: # Tiêu đề nhóm
                        current_group = text
                    elif "css-19vrbri" in cls: # Hàng dữ liệu
                        # Tách dòng bằng newline vì cấu trúc div lồng nhau
                        lines = text.split('\n')
                        if len(lines) >= 2:
                            k, v = lines[0].strip(), lines[1].strip()
                            product_specs[f"{current_group} > {k}"] = v
                
                result["specifications"] = json.dumps(product_specs, ensure_ascii=False)
            else:
                print(f"❌ Không tìm thấy bảng cho: {url[:40]}")

            # Ghi file luôn
            writer.writerow(result)
            f_handle.flush()

        except Exception as e:
            writer.writerow(result)
            f_handle.flush()
        finally:
            await page.close()

async def main():
    if not os.path.exists(INPUT_FILE):
        print(f"❌ Thiếu file {INPUT_FILE}"); return

    df = pd.read_csv(INPUT_FILE)
    df = df[df['url'].str.contains('phongvu.vn', na=False)]
    all_urls = df["url"].dropna().unique().tolist()

    # Resume logic
    done_urls = set()
    if os.path.exists(OUTPUT_FILE):
        try:
            df_done = pd.read_csv(OUTPUT_FILE, usecols=["url"])
            done_urls = set(df_done["url"].tolist())
        except: pass
    
    pending_urls = [u for u in all_urls if u not in done_urls]
    print(f"✅ Đã xong: {len(done_urls)} | ⏳ Còn lại: {len(pending_urls)}")

    with open(OUTPUT_FILE, 'a', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=["url", "product_name", "current_price", "product_code", "category", "specifications"])
        if os.stat(OUTPUT_FILE).st_size == 0 if os.path.exists(OUTPUT_FILE) else True:
            writer.writeheader()

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context()
            sem = asyncio.Semaphore(MAX_TABS)
            
            tasks = [scrape_one(context, url, sem, writer, f) for url in pending_urls]
            for f_task in tqdm(asyncio.as_completed(tasks), total=len(tasks), desc="Xúc Màn Hình"):
                await f_task
                
            await browser.close()

if __name__ == "__main__":
    asyncio.run(main())