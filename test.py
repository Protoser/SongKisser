from radio_browser import RadioBrowser

def find_station_url(station_name):
    results = RadioBrowser.search_radio(station_name)
    if results:
        station = results[0]
        print(f"Station: {station.get('name')}")
        print(f"Stream URL: {station.get('url')}")
    else:
        print("No station found with that name.")

if __name__ == "__main__":
    name = input("Enter the station name: ")
    find_station_url(name)
