import uvicorn


def main():
    uvicorn.run(
        "paid_art_cdn:app",
        host="0.0.0.0",
        port=4444,
        reload=False,
    )


if __name__ == "__main__":
    main()
