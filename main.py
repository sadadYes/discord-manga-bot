import discord
from discord import app_commands
from discord.ui import View, Button
import requests
import time

# Bot setup
TOKEN = ''

# Cache dictionaries
manga_cache = {}
chapter_cache = {}
chapter_images_cache = {}

# Cache timeout (in seconds)
CACHE_TIMEOUT = 3600  # Cache for 1 hour

class MangaBot(discord.Client):
    def __init__(self):
        super().__init__(intents=discord.Intents.default())
        self.tree = app_commands.CommandTree(self)

    async def on_ready(self):
        print(f'Logged in as {self.user}')
        await self.tree.sync()

client = MangaBot()

# Function to cache data
def cache_data(cache, key, value):
    cache[key] = {'timestamp': time.time(), 'data': value}

# Function to get cached data
def get_cached_data(cache, key):
    if key in cache:
        # Check if the cache is still valid
        if time.time() - cache[key]['timestamp'] < CACHE_TIMEOUT:
            return cache[key]['data']
        else:
            del cache[key]  # Remove expired cache
    return None

# Function to fetch manga search results from MangaDex API
def search_manga(title):
    cached_result = get_cached_data(manga_cache, title)
    if cached_result:
        print("Returning cached manga search results.")
        return cached_result
    
    search_url = f'https://api.mangadex.org/manga?title={title}'
    response = requests.get(search_url)
    if response.status_code == 200:
        data = response.json().get('data', [])
        cache_data(manga_cache, title, data)
        return data
    return []

# Function to fetch all chapters for a specific manga
def get_all_chapters(manga_id):
    cached_result = get_cached_data(chapter_cache, manga_id)
    if cached_result:
        print("Returning cached chapter list.")
        return cached_result

    chapters = []
    offset = 0
    limit = 100  # Fetch up to 100 chapters per request (max allowed by API)

    while True:
        chapter_url = f'https://api.mangadex.org/chapter?manga={manga_id}&translatedLanguage[]=en&limit={limit}&offset={offset}'
        chapter_response = requests.get(chapter_url)
        if chapter_response.status_code == 200:
            chapter_data = chapter_response.json()
            if 'data' in chapter_data and chapter_data['data']:
                chapters.extend(chapter_data['data'])
                offset += limit  # Move to the next batch
                if len(chapter_data['data']) < limit:
                    break  # Stop if less than the limit, meaning we've fetched all available chapters
            else:
                break  # No more chapters found
        else:
            print(f"Error: {chapter_response.status_code}")
            return None

    # Sort chapters by chapter number, handling missing and non-numeric chapters
    chapters = sorted(chapters, key=lambda x: (x['attributes']['chapter'] is None, float(x['attributes']['chapter'] or 'inf')))

    cache_data(chapter_cache, manga_id, chapters)
    return chapters

# Function to fetch chapter images from MangaDex API
def fetch_chapter_images(chapter_id):
    cached_result = get_cached_data(chapter_images_cache, chapter_id)
    if cached_result:
        print("Returning cached chapter images.")
        return cached_result

    chapter_images_url = f'https://api.mangadex.org/at-home/server/{chapter_id}'
    images_response = requests.get(chapter_images_url)
    if images_response.status_code == 200:
        images_data = images_response.json()
        base_url = images_data['baseUrl']
        chapter_hash = images_data['chapter']['hash']
        image_filenames = images_data['chapter']['data']
        image_urls = [f'{base_url}/data/{chapter_hash}/{filename}' for filename in image_filenames]
        cache_data(chapter_images_cache, chapter_id, image_urls)
        return image_urls
    else:
        print(f"Error retrieving chapter images: {images_response.status_code}")
        return None

# View for displaying and navigating through manga search results
class MangaSelectView(View):
    def __init__(self, interaction, mangas, page=0):
        super().__init__(timeout=None)
        self.interaction = interaction
        self.mangas = mangas
        self.page = page
        self.update_view()

    def update_view(self):
        self.clear_items()

        start = self.page * 10
        end = start + 10
        page_mangas = self.mangas[start:end]
        embed = discord.Embed(title="Select a Manga", description="\n".join(
            [f"{i + 1}. {manga['attributes']['title'].get('en', 'Unknown Title')}" for i, manga in enumerate(page_mangas)]
        ))

        for i, manga in enumerate(page_mangas):
            manga_id = manga['id']
            manga_button = Button(label=f"Select {i + 1}", style=discord.ButtonStyle.primary)
            manga_button.callback = self.create_callback(manga_id)
            self.add_item(manga_button)

        if self.page > 0:
            prev_button = Button(label="Previous Page", style=discord.ButtonStyle.secondary)
            prev_button.callback = self.prev_page
            self.add_item(prev_button)

        if len(self.mangas) > end:
            next_button = Button(label="Next Page", style=discord.ButtonStyle.secondary)
            next_button.callback = self.next_page
            self.add_item(next_button)

        return embed

    def create_callback(self, manga_id):
        async def callback(interaction):
            chapters = get_all_chapters(manga_id)
            if chapters:
                view = ChapterSelectView(interaction, manga_id, chapters)
                embed = view.update_view()
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                await interaction.response.edit_message(content="No chapters found for this manga.")
        return callback

    async def prev_page(self, interaction):
        self.page -= 1
        embed = self.update_view()
        await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction):
        self.page += 1
        embed = self.update_view()
        await interaction.response.edit_message(embed=embed, view=self)

# View for selecting chapters
class ChapterSelectView(View):
    def __init__(self, interaction, manga_id, chapters, page=0):
        super().__init__(timeout=None)
        self.interaction = interaction
        self.manga_id = manga_id
        self.chapters = chapters
        self.page = page
        self.update_view()

    def update_view(self):
        self.clear_items()

        start = self.page * 10
        end = start + 10
        page_chapters = self.chapters[start:end]
        embed = discord.Embed(title="Select a Chapter", description="\n".join(
            [f"Chapter {chapter['attributes']['chapter'] or 'N/A'}" for chapter in page_chapters]
        ))

        for i, chapter in enumerate(page_chapters):
            chapter_index = start + i  # Adjust the index to point to the correct chapter in the full list
            chapter_button = Button(label=f"Select {i + 1}", style=discord.ButtonStyle.primary)
            chapter_button.callback = self.create_callback(chapter_index)
            self.add_item(chapter_button)

        if self.page > 0:
            prev_button = Button(label="Previous Page", style=discord.ButtonStyle.secondary)
            prev_button.callback = self.prev_page
            self.add_item(prev_button)

        if len(self.chapters) > end:
            next_button = Button(label="Next Page", style=discord.ButtonStyle.secondary)
            next_button.callback = self.next_page
            self.add_item(next_button)

        return embed

    def create_callback(self, chapter_index):
        async def callback(interaction):
            chapter_id = self.chapters[chapter_index]['id']
            chapter_images = fetch_chapter_images(chapter_id)
            if chapter_images:
                view = ChapterImageView(interaction, chapter_images, chapter_id, self.chapters, chapter_index)
                embed = view.update_view()
                await interaction.response.edit_message(embed=embed, view=view)
            else:
                await interaction.response.edit_message(content=f"No images found for Chapter {chapter_id}.")
        return callback

    async def prev_page(self, interaction):
        self.page -= 1
        embed = self.update_view()
        await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction):
        self.page += 1
        embed = self.update_view()
        await interaction.response.edit_message(embed=embed, view=self)

# View for displaying chapter images and navigating through them
class ChapterImageView(View):
    def __init__(self, interaction, chapter_images, chapter_id, chapters, chapter_index, page=0):
        super().__init__(timeout=None)
        self.interaction = interaction
        self.chapter_images = chapter_images
        self.chapter_id = chapter_id
        self.chapters = chapters
        self.chapter_index = chapter_index
        self.page = page
        self.update_view()

    def update_view(self):
        self.clear_items()

        current_chapter = self.chapters[self.chapter_index]
        chapter_title = current_chapter['attributes']['chapter'] or 'N/A'
        embed = discord.Embed(
            title=f"Chapter {chapter_title}",  # Dynamically set the chapter title
            description=""
        )
        embed.set_image(url=self.chapter_images[self.page])
        embed.set_footer(text=f"Page {self.page + 1} out of {len(self.chapter_images)}")  # Set the footer using set_footer()

        # Navigation buttons
        if self.page > 0:
            prev_page_button = Button(label="Previous Page", style=discord.ButtonStyle.secondary)
            prev_page_button.callback = self.prev_page
            self.add_item(prev_page_button)

        if self.page < len(self.chapter_images) - 1:
            next_page_button = Button(label="Next Page", style=discord.ButtonStyle.secondary)
            next_page_button.callback = self.next_page
            self.add_item(next_page_button)
        else:
            if self.chapter_index < len(self.chapters) - 1:
                next_chapter_button = Button(label="Next Chapter", style=discord.ButtonStyle.primary)
                next_chapter_button.callback = self.next_chapter
                self.add_item(next_chapter_button)

        end_session_button = Button(label="End Session", style=discord.ButtonStyle.danger)
        end_session_button.callback = self.end_session
        self.add_item(end_session_button)

        return embed


    async def prev_page(self, interaction):
        self.page -= 1
        embed = self.update_view()
        await interaction.response.edit_message(embed=embed, view=self)

    async def next_page(self, interaction):
        self.page += 1
        embed = self.update_view()
        await interaction.response.edit_message(embed=embed, view=self)

    async def next_chapter(self, interaction):
        # Move to the next chapter
        self.chapter_index += 1
        next_chapter = self.chapters[self.chapter_index]
        next_chapter_id = next_chapter['id']
        chapter_images = fetch_chapter_images(next_chapter_id)
        if chapter_images:
            self.chapter_images = chapter_images
            self.page = 0
            self.chapter_id = next_chapter_id
            embed = self.update_view()
            await interaction.response.edit_message(embed=embed, view=self)
        else:
            await interaction.response.send_message("Error: Could not retrieve the next chapter images.")

    async def end_session(self, interaction: discord.Interaction):
        await interaction.response.edit_message(content="Thank you for reading!", embed=None, view=None)

# Register slash command for manga search
@client.tree.command(name="read", description="Search and read a manga by title.")
async def read(interaction: discord.Interaction, title: str):
    mangas = search_manga(title)
    if mangas:
        view = MangaSelectView(interaction, mangas)
        embed = view.update_view()
        await interaction.response.send_message(embed=embed, view=view)
    else:
        await interaction.response.send_message(f"No manga found with the title '{title}'.")

client.run(TOKEN)
