# RemoteWheel v0.2.5 - UI Overhaul, Modern SVG Icons & Enhanced Landscape Responsiveness 📱🏎️✨

Atualização incremental com foco em elegância visual, usabilidade e responsividade impecável em dispositivos móveis tanto no modo paisagem quanto em telas de diferentes proporções.

---

### 🎨 Novidades da Versão 0.2.5

#### 1. 📐 Redesign & Enquadramento Responsivo do Modal de Configurações
- Corrigido o corte das bordas superior e inferior que ocorria em certos aparelhos em modo paisagem.
- Altura inteligente calculada dinamicamente (`height: 94vh`) com `padding: clamp(...)` e `border-radius: 18px`.
- Fundo translúcido refinado com efeito de desfoque (`backdrop-filter: blur(8px)`).
- Barra superior de navegação com rolagem horizontal contínua sem quebras de linha.

#### 2. ⚡ Ícones Vetoriais SVG Integrados
- Substituição de emojis por ícones SVG vetoriais nítidos e padronizados em todas as abas:
  - 🎛️ **Sensibilidade**
  - 📂 **Perfis**
  - 🏎️ **Telemetria**
  - 🎨 **Temas**
  - 🔘 **Botões Visíveis**
- Novos ícones no botão de fechar (`✕`), `+ Novo Perfil`, `💾 Salvar` e `SALVAR & APLICAR`.

#### 3. 🏷️ Cards Modernos de Perfis Salvos
- Lista de perfis com ícones contextuais por categoria:
  - 🏎️ Carro esportivo para Corrida (*The Crew / Forza*).
  - 🎯 Mira para Jogos de Tiro (*GTA V / CS2 / Cyberpunk*).
  - 🎮 D-Pad clássico para Jogos Casuais (*FIFA / Rocket League*).
- Tag de status `ATIVO` e botão `Usar` com cantos suaves e resposta tátil.

#### 4. 📦 Pacote Windows & APK Atualizados
- Executável autônomo Windows `RemoteWheel.exe` gerado via PyInstaller com os novos assets embutidos.
- APK Android recompilado e otimizado pronto para instalação.

---

### 📥 Links de Download

- **Windows (Sem necessidade de Python):** Baixe e extraia `RemoteWheel-v0.2.5-Windows.zip` e execute `RemoteWheel.exe`.
- **Android:** Instale o `RemoteWheel.apk` diretamente no seu celular ou Smart TV.
