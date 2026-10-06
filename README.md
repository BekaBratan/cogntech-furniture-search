# Ақылды жиһаз іздеу және бөлме дизайны

Streamlit прототипі: каталогтан қазақша/орысша сұраумен іздеу және жиһазды 2D бөлме жоспарына орналастыру.

## Мүмкіндіктер
- Multilingual E5-small, категория/түс/стиль/бюджет/өлшем сүзгілері.
- Қысқа жад: соңғы сұрау/жоспар. Ұзақ жад: жасырылған тауарлар мен жоспарлар SQLite ішінде.
- Тіктөртбұрышты жатын бөлме, қонақ бөлме және кабинет.
- Каталогтан бюджетке сай жиһаз жиынтығы, негізгі және қосымша категориялар.
- Категория жетіспесе: бар тауармен ішінара жоспар, үлгілік жиһазбен толықтыру немесе толық жиынтықты талап ету.
- Бұлттағы Groq AI, жергілікті Ollama Qwen және бөлек AI емес алгоритм режимі.
- AI prompt ішінде бөлме түріне сәйкес екі тексерілген орналастыру мысалы. Бұл LayoutGPT-тегі in-context planning идеясына бейімделген тәсіл; ресми LayoutGPT репозиторийінің іске асыруы емес.
- Геометрия/ID/бос аймақтарды тексеру және 3 түзету әрекеті.
- PNG/JSON экспорт, схема жанындағы тауар карточкалары.

## Іске қосу
```bash
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

Сол жақ мәзірден Room design ашыңыз. Streamlit Cloud негізгі кіру файлы: app.py.

## Бұлттағы AI
Streamlit Settings → Secrets:
```toml
GROQ_API_KEY = "өз-кілтініз"
GROQ_MODEL = "openai/gpt-oss-20b"
```

Кілтті GitHub-қа жүктемеңіз. Groq Free Plan лимиттері қолданылады; API кілтсіз алгоритм режимі жұмыс істейді. Қосымша нұсқаулық: README_STREAMLIT.md.

## Каталог
catalog.xlsx және images/ қолданылады. Каталогты қолданушы кеңейтеді. Жатын бөлменің негізгі категориялары bed және wardrobe, қонақ бөлменікі sofa. Әдепкі режим каталогта барымен ішінара жоспар жасайды. Үлгілік режимде жетіспейтін негізгі категорияларға прототип өлшеміндегі объект қосылады; ол сатып алынатын тауар емес және бағасы белгісіз. Мұндай жоспарда тек каталог тауарларының бағасы есептеледі, толық бюджет расталмайды.

Өлшемдер сантиметрмен, жиһаздың толық сыртқы width_cm × depth_cm өлшемі. Стиль кодтары: minimalist, scandinavian, loft, classic, modern; бірнеше мән нүктелі үтірмен бөлінеді. room_types: bedroom; living_room; office. Толық схема README_ROOM.md ішінде.

## Шектеулер
Қолжетімділік және баға — каталогтағы мәндер, нақты уақыттағы дүкен қоры емес. Түс пен стиль бөлек. Есік/терезе орны қолмен бос аймақ ретінде беріледі. Жоспар кәсіби құрылыс сызбасы емес; барлық жүру жолы байланыстылығы мен төсектің екі бүйірі тексерілмейді. Жиынтық пен орналастыру іздеуі шектелген, глобалды оптимумға кепіл жоқ. Бұлтта SQLite сақтау ұзақтығы кепілденбейді. Бір ортақ демо профиль қолданылады.

## Тесттер
```bash
python -m unittest test_room_engine -v
```
HTTP жауаптары тесттерде имитацияланады. Нақты AI генерациясын API кілтімен бөлек тексеру қажет.


### Catalog update (140 products)
Both pages share catalog_io.py: comma decimals are normalized, image_file is respected, missing pictures are allowed. Seven search categories: bed, wardrobe, kitchen_cabinets, dining_table, tv, sofa, dresser. Room selection supports bedroom, living_room, office, kitchen and dining_room; televisions need mounting/support logic and are search-only.
Some catalog dimensions/style/availability are estimated and 89 links point to category pages; cards expose data_notes and distinguish category links from product links.
Old image blobs are ignored using legacy_image_hashes.json because IDs P001–P015 were reassigned. Upload replacement images to the image_file paths; new file content becomes visible automatically. Old pictures are retained.
SQLite memory is scoped by the catalog content hash to prevent old hidden IDs from hiding unrelated products. Editing the catalog starts a new memory scope.


### Layout improvements
Living rooms also consider wardrobes, dressers and dining tables. Candidate selection reserves smaller sets so optional pieces do not exclude every geometric plan.
Models receive a validated algorithm layout as a starting point and may improve it. Invalid model geometry raises a geometry error, not an API permission error. Optional algorithm fallback is labelled explicitly as non-AI.
The floor plan has no 300px image height cap; use the full-width toggle for a larger view. Numbered blocks correspond to the furniture list.
