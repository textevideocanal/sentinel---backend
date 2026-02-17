if __name__ == "__main__":
    import uvicorn
    
    # Pega a porta do Render ou usa 10000 como padrão
    port = int(os.getenv("PORT", 10000))
    
    logger.info(f"Iniciando uvicorn na porta {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)

