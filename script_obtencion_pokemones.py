import os
import time
import requests
from bs4 import BeautifulSoup
#https://pokemondb.net/pokedex/all

def descargar_pokedex_hd():
    url_base = "https://pokemondb.net"
    url_lista = "https://pokemondb.net/pokedex/all"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
    }
    
    output_dir = "pokemon_artwork_hd"
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    print("Obteniendo lista de Pokémon...")
    try:
        response = requests.get(url_lista, headers=headers, timeout=15)
        soup = BeautifulSoup(response.text, 'html.parser')
        # Buscamos todos los enlaces a las fichas individuales
        enlaces = soup.select('td.cell-name a.ent-name')
    except Exception as e:
        print(f"Error al conectar: {e}")
        return

    print(f"Se encontraron {len(enlaces)} Pokémon. Iniciando descarga de alta resolución...")

    # Usamos un set para evitar descargar el mismo Pokémon varias veces (formas repetidas)
    descargados = set()

    for link in enlaces:
        nombre_pokemon = link.text.strip().lower()
        if nombre_pokemon in descargados:
            continue
            
        url_ficha = url_base + link['href']
        
        try:
            # Entramos a la ficha individual (ej: /pokedex/slowbro)
            res_ficha = requests.get(url_ficha, headers=headers, timeout=10)
            soup_ficha = BeautifulSoup(res_ficha.text, 'html.parser')
            
            # Buscamos el enlace al "Official Artwork" que viste en tu captura
            # Normalmente está en un enlace con rel="lightbox"
            img_tag = soup_ficha.find('a', rel='lightbox')
            
            if img_tag and img_tag.get('href'):
                img_url = img_tag['href']
                
                # Descargamos la imagen de alta resolución
                img_data = requests.get(img_url, headers=headers, timeout=10).content
                
                filename = f"{nombre_pokemon}.jpg"
                filepath = os.path.join(output_dir, filename)
                
                with open(filepath, 'wb') as f:
                    f.write(img_data)
                
                print(f"Éxito: {nombre_pokemon} HD descargado.")
                descargados.add(nombre_pokemon)
                
                # Pausa mínima para no saturar el servidor
                time.sleep(0.5) 
            else:
                print(f"No se encontró artwork para {nombre_pokemon}")

        except Exception as e:
            print(f"Error procesando {nombre_pokemon}: {e}")

    print(f"\n¡Finalizado! Imágenes guardadas en: {output_dir}")

if __name__ == "__main__":
    descargar_pokedex_hd()