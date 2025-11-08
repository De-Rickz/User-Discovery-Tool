print(f"example.py loaded — __name__ = {__name__}")

def main():
    print("Running main() inside example.py")

if __name__ == "__main__":
    print("example.py is being run directly!")
    main()
