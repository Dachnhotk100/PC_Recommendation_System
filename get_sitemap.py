from curl_cffi import requests
from bs4 import BeautifulSoup
import pandas as pd

def get_desktop_links(sitemap_url):
    print(f"🚀 Đang quét sitemap Máy tính để bàn: {sitemap_url}")
    
    # Dùng session giả lập Chrome 120 để vượt tường lửa
    session = requests.Session(impersonate="chrome120")
    
    try:
        response = session.get(sitemap_url)
        # Sử dụng 'xml' parser
        soup = BeautifulSoup(response.content, 'xml')
        
        # Lấy tất cả các đường dẫn trong thẻ <loc>
        links = [loc.text for loc in soup.find_all('loc')]
        return links
        
    except Exception as e:
        print(f"❌ Lỗi khi lấy link: {e}")
        return []

# URL của sitemap Máy tính để bàn
url_may_bo = "https://phongvu.vn/sitemap_collection_products_4-man-hinh-may-tinh.xml"
desktop_links = get_desktop_links(url_may_bo)

if desktop_links:
    print(f"✅ Đã lấy được {len(desktop_links)} link màn hình máy tính.")

    # Lưu ra file CSV
    df = pd.DataFrame(desktop_links, columns=["url"])
    df.to_csv("man_hinh_may_tinh_urls.csv", index=False)
    
    print("📁 Đã lưu file: man_hinh_may_tinh_urls.csv")
    print("🎉 BƯỚC 1 ĐÃ HOÀN TẤT TRỌN VẸN!")