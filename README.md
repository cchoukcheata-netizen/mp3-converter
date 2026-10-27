# Media Converter 🎵🎬

គេហទំព័របម្លែងឯកសារទៅជា MP3 / WAV / MP4 ហើយរក្សាទុកក្នុងបណ្ណាល័យ។

## មុខងារ
- 📁 Upload ឯកសារវីដេអូ/សំឡេង → **MP3**, **WAV** ឬ **MP4**
- 🔗 បិទភ្ជាប់តំណ **Facebook** ឬ **YouTube** (សម្រាប់មាតិកាដែលអ្នកមានសិទ្ធិទាញយកប៉ុណ្ណោះ) → MP3 / WAV / MP4
- 🎙️ ថតសំឡេងតាម microphone → MP3 / WAV
- 📚 បណ្ណាល័យ: ស្តាប់/មើល ទាញយក លុប និងបើក **តំណដើម** (ថតរក្សាទុក `library/`)
- 📱 រចនាសម្រាប់ទូរស័ព្ទ និងកុំព្យូទ័រ

## ដំឡើង និងដំណើរការ
1. ដំឡើង Python 3.9+ និង **ffmpeg**
   - Windows: `winget install ffmpeg`
   - macOS: `brew install ffmpeg`
   - Ubuntu: `sudo apt install ffmpeg`
2. ```bash
   pip install -r requirements.txt
   python app.py
   ```
3. បើក http://localhost:5000

## កំណត់ចំណាំ
- ការថតសំឡេងត្រូវការ **HTTPS** ឬ **localhost**។
- បើ YouTube/Facebook ទាញយកមិនបាន សូមអាប់ដេត: `pip install -U yt-dlp`
- MP4 ពីឯកសារដែលគ្មានវីដេអូ (សំឡេងសុទ្ធ) មិនអាចធ្វើបានទេ។
- សូមប្រើសម្រាប់មាតិកាដែលអ្នកមានសិទ្ធិប៉ុណ្ណោះ។
