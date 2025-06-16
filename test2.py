import zipfile

bin_path = "Условия_размещения_ценных_бумаг_EC4556.bin"
zip_path = bin_path.replace(".bin", ".zip")

# Переименуем в zip для удобства
import os
os.rename(bin_path, zip_path)

# Распакуем содержимое
with zipfile.ZipFile(zip_path, 'r') as zip_ref:
    zip_ref.extractall("unzipped")
    print("✅ Распаковано в папку 'unzipped'")

# Выведем список файлов
print("\n📂 Содержимое архива:")
for name in zip_ref.namelist():
    print("—", name)
