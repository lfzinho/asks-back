# Roteiro da demonstração (5 minutos)

A fala do pitch está na tour (`/tour`, tecla **N** mostra as notas de cada slide). Este roteiro diz o que fazer na tela durante a parte de produto (B, 1:05–3:05) e como preparar tudo antes.

Funciona igual no **modo mock** (sem IA: leitura local da caligrafia e pistas escritas pelo professor) e com **um modelo real** (`--model claude` ou `--model openrouter`). Com modelo real, só muda a redação das perguntas e o julgamento das respostas.

A turma demo é a prova **“Everyday Science: Quiz 3”** (o app está em inglês): quatro questões de múltipla escolha e três abertas. A questão 5 é a do pitch: *How does an airplane fly? Explain why.*

## Antes de gravar

```bash
# terminal 1, raiz do repositório
firebase emulators:start --only auth,firestore,storage,hosting
```

```bash
# terminal 2, worker/
uv run python -m asksback worker --emulator --model mock
```

Três janelas:

- **A, a tour:** <http://127.0.0.1:5002/tour>
- **B, o professor:** <http://127.0.0.1:5002/teacher>. Entre (Google, ou e-mail e senha), clique em **＋ Demo class** e espere os 15 colegas simulados aparecerem (uns 5 s).
- **C, o aluno:** <http://127.0.0.1:5002/student> numa janela estreita ou anônima. Não entre ainda.

Deixe a página **Scan papers** da turma demo aberta no celular ou numa quarta janela.

No site publicado (`test-scanner-a42.web.app`) o fluxo é o mesmo, mas precisa de um worker ligado ao projeto (veja o README) e os alunos entram com a própria conta Google.

## 1:05–1:35 · Captura (slide “Captura”)

Clique em **Upload demo photos** (ou fotografe as cinco provas impressas). Vá para a janela do professor:

> Dez fotos, em qualquer ordem, uma de cabeça para baixo. Cada uma é casada com a página, o nome é lido do papel e as respostas são corrigidas pela rubrica.

## 1:35–2:00 · Gatilhos (slide “Gatilhos”)

Na tabela de alunos, aponte a coluna **Follow-up**:

- **Ana:** nada, a prova dela basta.
- **Bruno:** Q5 G1, Q6 G1, Q7 G2. Ele escreveu só *“The wing pushes the air down.”*: certo, sem justificativa.
- **Carla:** dois equívocos conhecidos (G4): o “caminho mais longo” por cima da asa e o “frio da água que entra no corpo”.
- **Diego:** Q5 ambígua (G3) e “o gelo boia porque é cheio de ar” (G4).
- **Eva:** Q7 G5. A resposta dela sobre o gelo é muito mais elaborada que as outras.

> A IA não acusa ninguém. Ela só aciona a verificação.

## 2:00–2:35 · Verificação (slide “Verificação”)

Na janela C, o painel do ambiente local oferece os cinco alunos escaneados. Clique em **Bruno Lima** e depois em **Start**.

A primeira pergunta cita a resposta dele:

> *You wrote "The wing pushes the air down". What makes that true? Walk me through the reasoning behind it.*

Digite (são as mesmas respostas do roteiro automático):

1. *It just goes up.* → vem uma **pista** (N1): *“Re-read what you wrote, then think about what happens to the wing while it pushes the air.”*
2. *The wing is tilted, so when it pushes the air down, the air pushes the wing up.* → alcançou com uma pista implícita, então vem uma pergunta **sem ajuda** (transferência): *“How can a stunt plane fly upside down?”*
3. *It flies with the nose up, so the tilted wing still pushes air down.*
4. Q6: *The evaporating water takes heat from my skin.*
5. Q7: *A frozen lake: the ice stays on top and the fish live underneath.*

> Cinco respostas curtas, menos de três minutos. Ele precisou de uma pista implícita, e a ideia transferiu.

## 2:35–3:05 · Painel do professor (slide “Painel do professor”)

Clique em **Play scripted replies** para responder os outros quatro alunos escaneados.

> 25% da turma estava *Quase lá* atrás de uma nota baixa. Bruno tinha 7 de 11 e recuperou 88% dos pontos que faltavam com uma pista implícita.

Abra **Bruno Lima**: as três notas (escrita 7, mediada 10,5, potencial 88%), o perfil e o motivo, cada conversa com os níveis de ajuda.

Volte e abra **Eva Rocha**:

> Eva tirou nota máxima. A resposta dela sobre o gelo destoa do resto da prova, então ela recebeu um caso novo: o que aconteceria com um lago se o gelo afundasse. Ela não conseguiu aplicar a ideia. Perfil: *Verificar entendimento*, conversar com ela. Quem decide é o professor.

Dê seu parecer para o Bruno (*Almost there*): o painel passa a medir a concordância com o professor.

## Se algo der errado

- Selo **worker offline** no app do professor: reinicie o terminal 2.
- **Aluno sem nome** (o nome não foi lido): abra o aluno, escolha quem é e clique em **Save and send follow-up**.
- **O tempo de resposta acabou:** a sessão mostra *Time is up*; crie uma nova turma demo.
