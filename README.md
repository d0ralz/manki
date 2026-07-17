# 🐵MAnki
## 🚨ATTENTION🚨THIS PROJECT WAS ENTIRELY MADE WITH AI. IF YOU'RE AI-ALERGIC, CLOSE THIS REPO IMMEDIATELY!
An ai-powered tool for creating easy anki flashcards. Supports only Gemini API (cuz their api can be free)
>Im just sharing "my" code with others. I likely won't be developing it further cuz im too lazy for this
### How to use
<img width="1734" height="1122" alt="manki" src="https://github.com/user-attachments/assets/edfe3b94-b3be-49e3-92dc-bc244d45e666" />
You write (or paste) a new word into the program and the LLM generates json with the word itself, a sentence using it, a definition, a translation, and a search query for an image suitable for the mined word (its all by default, you can remove or add any new fields). Then AnkiConnect receives this json and creates a new card in anki. You can also select TTS service and image provider for words. Images are added to the card by copying any pictures to the clipboard

### Features
- Gemini Multiple API keys - (keys will automatically rotate upon encountering an error. if your free api key exceeds its limits)

- TTS - Google, Oxford and Cambridge (only eng for latter two)

- Image Provider - (Google Images, IStock, Unsplash, Shutterstock, Pexels, GettyImages, Adobe Stock, Alamy)

- A bit of customization - (theme, accent color, font)

### How to setup
1. First of all you need to add a gemini api key (or several). You can get your api key for free [here](https://aistudio.google.com/api-keys). After creating the key paste it into the program settings

2. After that synchronize anki and the program using the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) addon. Choose your deck and card model. If you want images and TTS for words choose audio and image field (dont forget to add TTS and image provider)

3. Now you need to edit default Prepared Prompt for your needs. You can add or remove some fields and give your instructions for LLM

after that you can try to mine your first word

gl
