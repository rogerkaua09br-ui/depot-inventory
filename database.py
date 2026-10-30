import sqlite3
from datetime import datetime

DB_NAME = "estoque.db"

def conectar():
    return sqlite3.connect(DB_NAME)

def inicializar_banco():
    conn = conectar()
    cursor = conn.cursor()
    
    # Tabela de Fornecedores
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS fornecedores (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            contato TEXT,
            email TEXT
        )
    """)
    
    # Tabela de Produtos
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS produtos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            codigo TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            categoria TEXT NOT NULL,
            custo REAL NOT NULL,
            preco_venda REAL NOT NULL,
            quantidade INTEGER NOT NULL,
            estoque_minimo INTEGER NOT NULL
        )
    """)
    
    # Tabela de Movimentações
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS movimentacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            produto_id INTEGER,
            tipo TEXT NOT NULL, -- 'ENTRADA', 'SAIDA'
            quantidade INTEGER NOT NULL,
            data_hora TEXT NOT NULL,
            FOREIGN KEY (produto_id) REFERENCES produtos (id)
        )
    """)
    
    conn.commit()
    conn.close()

def cadastrar_produto(codigo, nome, categoria, custo, preco, quantidade, estoque_minimo):
    conn = conectar()
    cursor = conn.cursor()
    try:
        cursor.execute("""
            INSERT INTO produtos (codigo, nome, categoria, custo, preco_venda, quantidade, estoque_minimo)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (codigo, nome, categoria, custo, preco, quantidade, estoque_minimo))
        conn.commit()
        return True
    except sqlite3.IntegrityError:
        return False
    finally:
        conn.close()

def listar_produtos():
    conn = conectar()
    cursor = conn.cursor()
    cursor.execute("SELECT id, codigo, nome, categoria, custo, preco_venda, quantidade, estoque_minimo FROM produtos")
    produtos = cursor.fetchall()
    conn.close()
    return produtos

def obter_metricas_dashboard():
    conn = conectar()
    cursor = conn.cursor()
    
    # Total de SKUs e Valor Total em Estoque
    cursor.execute("SELECT COUNT(*), SUM(quantidade * custo) FROM produtos")
    res_prod = cursor.fetchone()
    total_skus = res_prod[0] if res_prod[0] else 0
    stock_value = res_prod[1] if res_prod[1] else 0.0
    
    # Itens com estoque baixo ou igual ao mínimo
    cursor.execute("SELECT COUNT(*) FROM produtos WHERE quantidade <= estoque_minimo")
    res_baixo = cursor.fetchone()
    low_stock = res_baixo[0] if res_baixo[0] else 0
    
    conn.close()
    return total_skus, stock_value, low_stock