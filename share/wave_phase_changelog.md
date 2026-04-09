# 波動位相システム 変更ログ

| 日時 | 変更内容 | 対象ファイル |
|------|---------|-------------|
| 2026-04-02 14:15 | experiments.md の結論を修正: 文間辺の重み 0.5→0.7（session-wave.py採用値に合わせた） | wave_phase_experiments.md |
| 2026-04-02 14:28 | Step1+2実験スクリプト作成。ペア同期→K_ij循環(Step1) + 語句クラスタ強い力(Step2) | step12_experiment.py (新規) |
| 2026-04-02 14:35 | pair_syncをKuramotoだけでなくラプラシアン辺重みにも反映。A≠Bの差が出た。S7で+21%、語句エネルギー+15-30%。coupling=0でもS111浮上 | step12_experiment.py |
| 2026-04-02 14:50 | 未知語自己埋込み実験。15語のベクトルを剥がして5パス。pair_syncのみ+1.3% | unknown_word_experiment.py (新規) |
| 2026-04-02 14:58 | 位相近似ブースト追加（シオ提案）。収束位相+pair_syncから既知語ベクトルを借りて仮ベクトル生成。全体+26.4%、発展+44.8% | unknown_word_experiment.py |
| 2026-04-02 15:12 | 古典教育AI論文(8_1.pdf)のテキスト準備。OCR+コピペからクリーンナップ。本文161文 | 8_1_body.txt (新規) |
| 2026-04-02 15:20 | 2論文交互読み実験。教育→甘利→教育で+3559ペア増加。共通語「学習」が+13.6% | cross_paper_experiment.py (新規) |
| 2026-04-02 15:40 | 衝突検出実験。「過程」Δ=2.14, 「評価」Δ=1.89等。衝突→周辺伝播r=0.332（染み出し） | collision_experiment.py, collision_neighbor.py (新規) |
| 2026-04-02 15:54 | 位相シフト実験。ランク変化18.6%あるが改善方向には不十分(-0.4%)。蓄積量不足の可能性 | phase_shift_experiment.py (新規) |
| 2026-04-03 15:01 | ワーキングメモリ+長期記憶DB設計・実装。SQLite 1つでworking_*/long_term_*テーブル分離。WALモード+UPSERT | db/phase_state.db (新規), reading_session.py (新規) |
| 2026-04-03 15:05 | reading_session.py完成。1文ずつ読み→WM書込→consolidateで長期に焼く。甘利論文150文を1.8秒で処理 | reading_session.py |
| 2026-04-03 15:11 | 2パス目で長期記憶ロード確認。衝突10829→5425(-50%)。学習が蓄積されている | reading_session.py |
| 2026-04-03 15:18 | 文ノード位相の保存を追加。working_sentence_phase + long_term_sentence_phase | reading_session.py, db/phase_state.db |
| 2026-04-03 15:22 | 位相のみで文内容復元実験。chiVe不使用でS121「多層,画像,処理,誤差,逆,回路,神経」を復元 | phase_reconstruct.py (新規) |
| 2026-04-03 15:25 | 繰り返し読み実験。S22を10回読むと全名詞のphase_distが0.03-0.07に収束 | repeat_read.py (新規) |
| 2026-04-03 15:28 | 符号付き位相差(signed phase diff)をpair_syncに追加。語順を位相差の符号で暗黙的に表現 | reading_session.py, db/phase_state.db |
| 2026-04-03 15:33 | pair_syncの対象を名詞→名詞+動詞+副詞+形容詞に拡張。ペア数3618→7629(+111%) | reading_session.py |
| 2026-04-04 07:37 | 未知語位相テスト。15語のベクトル剥がし→5パス学習。文明Δ=0.04(安定)、人類Δ=1.65(ドリフト) | unknown_phase_test.py (新規) |
| 2026-04-04 07:46 | 辞書的AI文8本を学習。新ペア(音声,画像,運転,パターン等)がsync=1.0で形成 | dict_learn_test.py (新規) |
| 2026-04-04 08:00 | chiVe完全不使用の位相のみ学習セッション実装。位相距離でクエリキュー生成 | phase_only_session.py (新規) |
| 2026-04-04 08:01 | 位相のみ3パスで衝突7023→4006に減少。chiVeなしでも位相が安定方向に収束 | phase_only_session.py |
| 2026-04-04 08:13 | 復元v2: 全品詞+signed語順推定。S79「処理→する→…→推論→統計的→完成」。S7語順もほぼ正確 | phase_reconstruct_v2.py (新規) |
| 2026-04-04 08:16 | 文脈学習復元: S78-80の3文×15パスでS79復元。signedが係り受け方向と一致 | context_reconstruct.py (新規) |
| 2026-04-04 08:37 | build_local_graphが文ノード位相をlong_termから読み込むように変更。文ノードもKuramoto参加 | reading_session.py |
| 2026-04-04 08:55 | 文ノードKuramoto Kスイープ(0.0-2.0)。K=0.3で隣接文が良好に同期、K≥0.5で振動 | (inline test) |
| 2026-04-04 08:57 | セクション境界検出: 同一セクション内距離0.27 vs 境界1.66-2.48。見出し除外でも2.25-2.79で明確 | (inline test) |
| 2026-04-04 09:29 | R値（mean resultant length）実装。累積方式→EMA方式に修正（崩壊問題解消） | reading_session.py, db/phase_state.db |
| 2026-04-04 09:30 | R-adaptive ETA実装: ETA_eff = ETA × R。カバー範囲広い語ほど動きにくい | reading_session.py |
| 2026-04-04 09:33 | feed_text.py作成。任意テキスト(ファイル)をトークン化して位相システムに投入 | feed_text.py (新規) |
| 2026-04-04 09:33 | 教育論文投入。「学習」R=0.905→0.721（カバー範囲拡大）、「脳」R不変（ドメイン外） | feed_text.py |
| 2026-04-04 10:00 | R値のEMA修正。15パスでもR=0.721で安定（旧方式は0.001に崩壊） | reading_session.py |
| 2026-04-04 10:17 | 設計ノート: 意味の読み替えと驚き検出。シオの洞察5点を記録 | wave_phase_experiments.md |
| 2026-04-04 10:58 | 設計ノート拡張: 4段階理解プロセス(S1-S4)。コスト昇順の段階的探索設計 | wave_phase_experiments.md |
| 2026-04-04 11:55 | ゼロスタート実験。全語phase=0→対称性破れず位相不動。pair_syncは学習された | zero_start.py (新規) |
| 2026-04-04 11:59 | 文字コード由来初期位相で対称性破れ成功。15パスでphase_std 1.6→0.8に収束。chiVeなしで復元成功 | zero_start.py |
| 2026-04-04 12:08 | reading form + Unicode文字種バイアスで初期位相生成。漢字/ひらがな/カタカナの視覚的違いが位相に反映 | zero_start.py |
| 2026-04-04 12:12 | 品詞フィルタなし(PAIR_POS=None)実装。ペア数7629→18591。助詞も全参加。復元品質は同等 | zero_start.py, reading_session.py |
| 2026-04-04 12:20 | 文字レベル位相学習実験。1文字=1ノード。「研←究」sync=0.999、小文字モーラ結合対応 | char_level_test.py (新規) |
| 2026-04-04 12:27 | sudachi reading_form/is_oov確認。「場合」と「ばあい」は読みバアイで一致。xyzzyもreading生成される | (inline test) |
| 2026-04-04 12:31 | 助詞の位相分析。「も」R=0.42(最広)、「が」R=0.99(固定位置)。位相で助詞の機能差が出る | (inline test) |
| 2026-04-04 12:34 | 教育論文追加で助詞位相が収束。「と」+0.73→+0.50、助詞クラスタが密に | (inline test) |
| 2026-04-04 12:38 | 助詞の前後位相シグネチャ分析。「は」中立、「が」「を」前後から離れる。平均では区別困難、pair_syncが本質 | (inline test) |
| 2026-04-04 12:48 | 助詞+前後ペアの3語パターン分析。「を」+動詞=前語に引かれる(接着)、「が」+動詞=後語を押す(能動) | (inline test) |
| 2026-04-04 12:56 | phrase_boostなし+一律α検証。助詞のsignedパターンは維持 → アーティファクトではなく本物 | (inline test) |
| 2026-04-04 14:30 | アブレーション実験(A0-A6)実行。評価指標v1はsigned diffの性質と不一致で50%に張り付き | ablation.py (新規), wave_phase_ablation.md (新規) |
| 2026-04-04 14:43 | Codex(GPT-5.4)に評価指標レビュー依頼。pairwise order acc, boundary AUROC等を提案される | (Codex review) |
| 2026-04-04 15:07 | 評価指標v2実装。order_scoreロジック(reconstruct_v2と同じ)でKendall tau-b | ablation.py |
| 2026-04-04 15:09 | v2結果: chiVe版のみtau=+0.252。ゼロスタートはtau負。chiVeの初期位相が語順の源泉と判明 | wave_phase_ablation.md |
| 2026-04-04 15:21 | A1(ランダム初期位相)長期学習。40パスでもtauゼロ振動。ダイナミクスだけでは語順学習不可 | wave_phase_ablation.md |
| 2026-04-04 15:25 | chiVe初期位相の分析。品詞ごとの位相分布が語順に一致（名詞=-2.0, 助詞=+0.4）。語順の正体は品詞依存的な符号パターン | wave_phase_ablation.md |
| 2026-04-04 15:41 | 順方向+逆方向パス比較。逆パスの効果は微増(tau+0.007)。追加学習でchiVe効果が薄まる | wave_phase_ablation.md |
| 2026-04-04 15:43 | 助詞最小対文テスト。58文×15パス。は/がのsigned diffに差。がの方が名詞との結合が強い | particle_test.py (新規), wave_phase_ablation.md |
| 2026-04-04 15:47 | 初期位相の影響確認。は=-1.04, が=+1.28（reading初期）。signed diffへの初期位相の影響の可能性 | wave_phase_ablation.md |
| 2026-04-04 16:54 | chiVe初期位相確認。は=+1.57, が=-1.57。main DBは助詞PAIR_POS除外で比較不可 | wave_phase_ablation.md |
| 2026-04-04 17:00 | 総合考察: 位相の独自貢献(語句化,R値,トピック距離,pair_sync) vs 入力/初期条件依存の整理 | wave_phase_ablation.md |
| 2026-04-04 17:14 | 品詞バイアス分離実験(A7/A8)。POS bias onlyでtau=+0.145(chiVeの58%)。語順の半分は品詞配置、残り半分は個別ベクトル | pos_bias_ablation.py (新規), wave_phase_ablation.md |
| 2026-04-04 17:36 | 意味の再定義: 「意味は独立チャネルではなく音と形の変形パターン」（シオの洞察）。3チャネル→2チャネルへの転換 | multimodal_phase_test.py (新規) |
| 2026-04-04 17:45 | 2チャネル(音韻+字形)v2。pair_syncを両チャネルに追加。助詞の曲がり方が助詞ごとに異なる（「を」は逆方向に曲がる） | multimodal_phase_v2.py (新規) |
| 2026-04-04 18:39 | 2チャネルで甘利論文150文を学習。chiVeなし。チャネル間で結びつきパターンが異なる（学習×連想=字形のみ、学習×関係=音韻のみ） | multimodal_full_test.py (新規) |
| 2026-04-04 18:45 | 同音異字/同字異音テスト。橋/箸(ハシ)等でaud_dist=0,vis_dist>0。5/5成功。2チャネル分離が機能 | homophone_test.py (新規) |
| 2026-04-04 18:56 | 文脈蓄積テスト。同音異義語を段落で学習、文間ペアも記録。橋と箸のpair_syncネットワークが完全分離。意味=チャネル差分×文脈的結びつき | context_homophone_test.py (新規) |
| 2026-04-04 19:17 | カタカナ曖昧性解消テスト。「ハシ」「ハナ」「カミ」を文脈だけで判定。1文単位14/14(100%)。1ストリーム10/14(71%、文境界混入で) | context_homophone_test.py |
| 2026-04-04 19:26 | 設計決定: R値は後回し。pair_syncだけで蓄積を賄う。R値は驚き検出が必要になったら復活 | (設計判断) |
| 2026-04-04 19:34 | 2-hop探索テスト。1-hop71%→2-hop79%に改善。全探索と近傍フィルタで差なし（語彙80語で小さいため）。拮抗ケースの2-hop経路は助詞経由で両候補に繋がる | context_homophone_test.py |
| 2026-04-04 19:54 | chiVeブートストラップ比較(A/B/C)。B(300次元偶奇分割)が強結合ペア1331で最良。ただしいずれ撹拌されるので本質的差はない | bootstrap_test.py (新規) |
| 2026-04-04 20:00 | 位相衝突調査。804語で閾値0.15に911ペア(0.28%)。システム×シナプスなど同文字種・同文字数で起きやすい。文脈で育てれば似た文脈の語が近くに集まるので問題なし | bootstrap_test.py (inline) |
| 2026-04-04 20:04 | zoom in判定の設計: 位相近傍→正規化→pair_syncで精密マッチ。S1-S4理解プロセスと合致 | (設計) |
| 2026-04-04 20:52 | zoom in判定の実装+2-hop追加。pair_syncが効くケースは良好（「人間×知能×超える→性能」）。位相近傍だけだとノイジー、2-hop必須 | zoom_resolve_test.py (新規) |
| 2026-04-04 20:59 | 語句化: 分散トラッキング追加。諺「急がば回れ」が全体h=0.92で語句検出。助詞パターンも差が出る（「を」が最硬） | phrase_variance_test.py (新規) |
| 2026-04-04 21:01 | 動的語句合成の設計: 分散だけ記録、合成はその都度。永続的統合より柔軟（「神経」が単体でも使える） | (設計) |
| 2026-04-04 21:11 | 2論文(甘利+教育)統合学習。308文1450語2.2秒。「フィードバック×生成AI」「国語科×言語」等が語句化 | two_paper_phrase_test.py (新規) |
| 2026-04-04 21:16 | ことわざエラー検出。語置換6/6(100%)検出、助詞入替4/5(80%)検出。エラー箇所にピンポイントでhardness=0の穴が開く | idiom_error_test.py (新規) |
| 2026-04-04 21:19 | 語順違反検出(signed diff)。正順/逆順で符号が反転（花より団子+0.09 vs 団子より花-0.09）。音韻チャネルで方向性検出可能 | order_violation_test.py (新規) |
| 2026-04-04 21:28 | データ量試算: 人間規模10万語500万ペアで約660MB。pair_syncにsigned追加してもペアあたり16バイト増のみ | (試算) |
| 2026-04-04 21:49 | 波動伝播+2チャネル。強ペア120→302(+152%)。チャネル乖離も増加。6倍遅い(0.7→6.0s) | wave_2ch_test.py (新規) |
| 2026-04-04 21:55 | 文の復元テスト(2ch+wave)。signed diffのtau≈0(品詞バイアスなし)。音韻連鎖記憶を追加→S22がtau+0.394に改善 | reconstruct_2ch_test.py (新規) |
| 2026-04-04 22:03 | 重点学習テスト。S79が-0.076→+0.205に改善。S121は悪化(共有語多すぎ) | reconstruct_2ch_test.py |
| 2026-04-04 22:10 | S121鬼学習200パス。-0.063→-0.209に悪化。step10で収束し改善しない。共有語の本質的限界 | s121_intensive_test.py (新規) |
| 2026-04-04 22:14 | 語句化+連鎖で語順復元。閾値0.3で語句tau+0.363(語レベル+0.012の30倍)。S22がtau+0.587 | phrase_chain_reconstruct.py (新規) |
| 2026-04-04 22:22 | クロスチェックループ。ヒルクライミング+swap。S7が-0.050→+0.150に改善。一部悪化 | crosscheck_reconstruct.py (新規) |
| 2026-04-04 22:28 | Codexレビュー: pair_syncが方向無し、cos値が全部0.9+で差がつかない、hardnessが二重カウント。signed方向+chain重み増を提案 | (Codex review) |
| 2026-04-04 22:31 | スコア関数v0-v3比較。v2(chain=0.6+signed dir)が平均+0.063で最良。S33が-0.196→+0.236に大改善 | crosscheck_reconstruct.py |
| 2026-04-04 22:38 | v3-v5追加比較。v5(chain+dir+stability/var)がavg-0.003で最安定。cos正規化より分散ベースが有効 | crosscheck_reconstruct.py |
| 2026-04-04 22:43 | ビームサーチ実装。beam(w=3)がavg+0.100で全手法中最良。4/5文でプラス。狭いビームほど良い | crosscheck_reconstruct.py |
| 2026-04-04 22:48 | 波動ビームサーチ実装。avg+0.006。S33/S79/S121でbeamに勝る（間接繋がりを波動が拾う）。短い文では弱い | crosscheck_reconstruct.py |
| 2026-04-04 22:53 | 長い文のtau低下は「暗記は無理ゲー」という人間的特性と一致。語順完全復元は求めず語句レベルの要旨復元で十分 | (考察) |
| 2026-04-04 23:04 | 設計決定: ビームサーチ廃止→波動一本化。暗記=音韻語句チェーンの自動再生、理解=波動伝播。スコア関数の手動設計を排除、辺重みが全部語る | (設計決定) |
| 2026-04-04 23:14 | 波動想起で文を特定するテスト。飽和問題あり（全ノードclip上限に張り付き） | wave_recall_test.py (新規) |
| 2026-04-04 23:16 | Codexレビュー: 次数正規化+tanh+top-K辺+再注入制限+z-score出力を提案 | (Codex review) |
| 2026-04-04 23:17 | Fix1(次数正規化)で飽和完全解消。Fix2(tanh)は差を潰す→不採用。Fix4(再注入制限)は信号弱すぎ→不採用。Fix5(z-score)でコントラスト増強 | wave_recall_test.py |
| 2026-04-04 23:24 | 波動想起+文特定テスト(次数正規化+z-score)。10クエリ全問正解。「記憶と連想」→S129「連想記憶モデルを用いて連想想起」等。chiVeなしで文想起が完全動作 | wave_recall_test.py |
| 2026-04-05 19:40 | 自発zoom-out検出をリング密度で実装。クエリ近傍スカスカ+外帯クラスタありを検出。神経回路で学習モデル計算層へ抽象化、AIで社会影響クラスタへ | zoom_out_test.py (新規) |
| 2026-04-05 19:45 | 「概念」を辞書20文で学習→nearが1から13に増える。関連学習が周辺にある「哲学」クエリもzoom-out発動で意味クラスタに飛べる | concept_dict_test.py (新規) |
| 2026-04-05 19:55 | あほ同音異義実験。別表記あほ/アホはsudachi別lemmaで完全分離。同表記「あほ」は1-hopで混ざるが2-hop先で愛情/罵倒経路に分かれる | aho_context_test.py (新規), aho_channel_split.py (新規) |
| 2026-04-05 20:02 | ほし2文脈(星/干し)のチャネル差テスト。STAR平均|Δ|=0.36、DRY=0.46で有意差なし。個別語では食べるa+0.87v-0.88等特徴あり | hoshi_channel_test.py (新規) |
| 2026-04-05 20:08 | 音素位相パイプライン実装。sudachi→reading→pyopenjtalk→音素列→位相。英語はカタカナ化、カナハッシュの文字バイアスを排除 | phoneme_phase.py (新規) |
| 2026-04-05 20:15 | wave_recall音素版。甘利150文を1.01秒学習、10クエリ全問正解。カタカナ版と同等性能 | wave_recall_phoneme.py (新規) |
| 2026-04-05 20:22 | 復元比較(KANA vs PHON)。avg tau 0.143 vs 0.147でほぼ差なし。でもS71「LLM言語扱う」でKANA-0.333→PHON+1.000の英語混在耐性 | reconstruct_phoneme_vs_kana.py (新規) |
| 2026-04-05 20:30 | 音素+アクセント(H/L)位相。pyopenjtalkフルコンテキストラベルからF_moraとF_accent抽出。橋箸端/星干し/あほアホ/雨飴/神髪が音韻だけで分離 | phoneme_accent_phase.py (新規) |
| 2026-04-05 20:35 | 橋箸端カタカナ判定テスト(ハシを文脈で判定)。12個別文で11/12(91.7%)正解。1文境界なしの単ストリームでもwindow±2で同じく91.7% | hashi_disambiguate.py (新規), hashi_single_stream.py (新規) |
| 2026-04-05 20:49 | 助詞を接続演算子として扱う試み(kuramoto接続媒介版)。前後語のsigned diff蓄積、論文学習追加しても4/12でランダム並み。助詞は意味が多様すぎて単一シフトに収束しない | hashi_particle_kuramoto.py (新規), hashi_particle_with_corpus.py (新規) |
| 2026-04-05 21:00 | 助詞の前後予測クラスタ実装(直前直後の語の位相平均)。kuramotoありだと全助詞クラスタがaud-2.4に収束、外すとR=0.05-0.5で分散しすぎ。6-7/12止まり | hashi_particle_predict.py (新規) |
| 2026-04-05 21:05 | 結論: 助詞演算子化は原理的に難しい。人間は映像/動作/触覚との結びつきで品詞クラスタが自然発生するが、テキストだけの位相ではgroundingが足りない。将来の方向: カメラ映像+image_embeddingsとの位相結合 | (考察) |
| 2026-04-05 21:15 | zoom-outクラスタ妥当性検証。凝集度ランダムより+0.5-1.2σ、Jaccard類似度0.00-0.09で意味的収束弱い。center語が機能語になる | zoom_out_validity.py (新規) |
| 2026-04-05 21:25 | Codex(GPT-5.4)レビュー: 学習/評価が同じコーパスで閉じてる、クエリ数少、outer閾値ズレ、ランダム基準固定、意味表現弱。改善: train/test分離、IDF、分位点、置換検定、外部gold | (Codex review) |
| 2026-04-05 21:30 | IDF+サイズ一致置換検定+分位点+gold clusterで再検証。center語が内容語に(単細胞、理論、好奇心、アーキテクチャー) | zoom_out_validity_v2.py (新規) |
| 2026-04-05 21:31 | near/outer分離評価。near P@12=0.1-0.4(goldと重なる)、outer P@12=0(別軸)。nearが類似想起、outerが抽象化/連想の2段目として役割分担 | zoom_out_validity_v2.py |
| 2026-04-05 22:00 | 学習時の自己組織化実装。各語が近隣top-10の位相平均方向に微シフト(always mode)。シオの懸念「潰れ」は起きず、phase_std保たれる | zoom_out_self_organize.py (新規) |
| 2026-04-05 22:05 | 自己組織化の効果検証。outer P@12 0.095→0.119(+25%)改善、phase_std 2.513→2.632で拡散方向、潰れない | zoom_out_self_organize.py |
| 2026-04-05 22:10 | 識別能力への影響テスト(橋/箸/端)。baseline 11/12(91.7%) → self-org 10/12(83.3%)で微劣化。候補間の差が薄まる副作用 | hashi_with_selforg.py (新規) |
| 2026-04-05 22:15 | 語順復元への影響。self-org rate=0.3で tau +0.208→+0.238 に+0.030改善。識別劣化とトレードオフだが総合的に得 | reconstruct_with_selforg.py (新規) |
| 2026-04-05 22:20 | 動的rate検証(volatility/cooling/docfreq)。volatility悪化(+0.199)、cooling等価(rate半減と同じ)、docfreq変化なし。どれもstaticに勝てず | reconstruct_with_selforg.py |
| 2026-04-05 22:25 | Codex(GPT-5.4)レビュー: 自己組織化の効果は「全語彙の一貫した弱い平滑化」が本質。rate動的化は更新を疎にするだけ。構造選択(引力の向きと対象)へゲートを移すべき | (Codex review) |
| 2026-04-05 22:28 | Codex提案の構造変更を実装(A:近塊抑制、B:top5+mid5、C:reaction再定義、AB/ABC)。A,B,ABはstaticと同等、Cは劣化。構造改善もstatic超えず | reconstruct_selforg_v2.py (新規) |
| 2026-04-05 22:30 | 決定: self-org static rate=0.3採用。語順復元改善+識別軽微劣化のトレードオフを受容 | (設計決定) |
| 2026-04-05 22:37 | 継続学習テスト(amari→edu同系論文)。どのvariantも劣化せずむしろ改善、シナジーあり | continual_learning_test.py (新規) |
| 2026-04-05 22:42 | 継続学習(amari→技術者倫理)ドメイン離れ版。BASELINE Δ-0.040大劣化、STATIC Δ-0.008、DYNAMIC(vola) Δ-0.005で最安定。dynamicがドメイン変化で優位 | continual_learning_test.py |
| 2026-04-05 22:43 | 設計決定: 継続学習はdynamic self-org採用(相対安定性) | (設計決定) |
| 2026-04-05 22:48 | 長期学習比較(15/30/60パス)。STATICが全期間で最良、DYNAMICは60パスで-0.062まで崩壊。volatilityが一部語を暴走させる副作用 | long_training_compare.py (新規) |
| 2026-04-05 22:53 | シナプスhomeostasis由来の一律decay試験。decay0.99でBASELINE tau +0.208→+0.234に向上、decay0.95は強すぎて下がる | continual_with_decay.py (新規) |
| 2026-04-05 22:58 | シオ提案: 反応度ベースのLTP/LTD式差分decay。touched=軽い減衰、untouched=強い減衰 | (設計) |
| 2026-04-05 23:00 | LTP/LTD decay実装(touched=0.99, untouched=0.90)。amari15+0.234、継続学習Δ-0.002で**過去最良**。self-orgなしでもこれ | continual_ltp_decay.py (新規) |
| 2026-04-05 23:02 | LTP/LTD decay全タスクテスト。amari15+0.234(改善)、amari60+0.131(変化なし)、hashi 11/12(識別維持)。**self-orgと違って識別を犠牲にしない** | ltp_decay_multitest.py (新規) |
| 2026-04-05 23:03 | 最終決定: LTP/LTD decay (touched=0.99, untouched=0.90) 採用。self-orgの代替として優秀、トレードオフなし | (設計決定) |
| 2026-04-05 23:30 | reading_session_v2.py 完成。2チャネル+LTP/LTD+wave_recall+selforg(optional)を統合、150文1秒学習、10/10クエリ正解 | reading_session_v2.py (新規) |
| 2026-04-06 00:05 | v2アブレーション試験 (8本)。degree正規化が最重要(wave 10/10→0/10で崩壊)、2チャネル統合が順序記憶の基盤、音素は補助、差分decay地味に効く、selforgはトレードオフ | ablation_v2_test.py (新規), wave_phase_ablation.md |
| 2026-04-06 00:25 | degree正規化9方式比較。sqrt(0.5乗)が明確sweet spot、pow075/cbrt/raw/min/logは全滅。グラフラプラシアン対称正規化が数学的最適 | wave_norm_compare.py (新規) |
| 2026-04-06 00:40 | row × selforg組合せ試験。WaveHits全構成10/10でsqrt/row同点、mrのみ差(sqrt=0.10, row=0.80-1.00)。Hashi/Continualは正規化非依存 | row_selforg_test.py (新規) |
| 2026-04-06 00:45 | 有向エッジ+row試験。undirected+sqrt=10/10 → directed+row=3/10に崩壊。片方向エッジ79%でsinkノード多発、波が戻らない。過去の「有向パス不採用」判断を定量確認 | directed_row_test.py (新規) |
| 2026-04-06 00:50 | v2 ablation 8構成 × row再走。7構成hits維持、no-accentだけ9/10に1miss。accent弱い時にrowのロバスト性劣化 | ablation_row_full.py (新規) |
| 2026-04-06 00:55 | タスク解離発見: sqrtがTopicP@10=0.43で優位、rowはOrderTau +0.075→+0.227(3倍)で優位。関連性と方向性は独立の軸 | row_topic_order_test.py (新規) |
| 2026-04-06 01:00 | ブレンド試験(force線形結合、β掃引)。β≥0.2で崖崩壊(hits 6/10, TopicP 0.14)。sqrt/row固有モードが非直交で干渉 | blend_test.py (新規) |
| 2026-04-06 01:03 | **シオ提案の重ね合わせ(独立伝播+観測時α合成)が成功**。α=0.2で hits 10→9、TopicP 0.43維持、OrderTau +0.075→+0.248(3倍) | superpose_test.py (新規) |
| 2026-04-06 01:05 | 決定: デュアル・ウェーブ(sqrt+row重ね合わせ、α=0.2)採用。干渉なしで両波情報を保持、観測時にタスク別α選択 | (設計決定) |
| 2026-04-06 01:15 | 物理輸入方針: シオ提案で波動方程式の物理学(グリーン関数・スペクトル・非エルミート等)を系統的に借りる | (方針決定) |
| 2026-04-06 01:17 | wave_recall線形性検証。u_A+u_B→cos_sim=1.0000、clip有無問わず完全線形。グリーン関数が使える | green_function_test.py (新規) |
| 2026-04-06 01:18 | グリーン関数G事前計算。100クエリ 8秒→0.05秒で160倍速。G対称、‖G-G.T‖=0、hits=10/10完全維持 | green_function_v2.py (新規) |
| 2026-04-06 01:24 | スパース正規化ラプラシアン化で583倍速。53秒→0.09秒、誤差4.99e-16で数値精度限界一致 | green_function_fast.py (新規) |
| 2026-04-06 01:27 | スペクトル分析。N=715でeigh 0.11秒、負固有値138個(反振動)、中位[100,300)200モードで10/10達成 | spectral_analysis.py (新規) |
| 2026-04-06 01:32 | バンドパス+周波数加工+row非エルミート+モード占有分析。row版G病的(Re(λ)=-1e17)、クエリは下位モード主活性 | spectral_deep.py (新規) |
| 2026-04-06 01:37 | モード可視化+副作用検証。rank0=助詞導管、rank714=「も」単独支配、中位圧縮はTopicP半減/OrderTau符号反転で不採用 | mode_inspect.py (新規) |
| 2026-04-06 01:43 | 非線形Duffing x³項掃引。β∈[-0.1,1.0]で線形同等、それ外は崩壊。hashi既に12/12で余地なし | nonlinear_test.py (新規) |
| 2026-04-06 01:47 | シオ提案「習熟度としての非線形」。ノード別β=maturity×β。ロバスト性25倍(崩壊閾値10→500)、助詞が自然に深井戸化 | maturity_nonlinear.py (新規) |
| 2026-04-06 01:49 | Hashi分離度テスト。明確12問全正解、β=100で分離度33%増(0.40→0.53)=確信度向上 | hashi_nonlinear.py (新規) |
| 2026-04-06 01:52 | マチュリティ非線形副作用検証。β=50が安全(WaveHits維持,TopicP微減,OrderTau微増)、β=100でトレードオフ | maturity_side_effects.py (新規) |
| 2026-04-06 02:00 | シオ提案「意識=迷いを決断に変えるプロセス」。クオリア=波動応答、意識=思考ループ+非線形エンジンと定式化 | (設計視点) |
| 2026-04-06 02:02 | 意識デモ: hashi step-by-step可視化。step2-4暫定→6-10迷い→12-15決断の思考ループが見える | consciousness_demo.py (新規) |
| 2026-04-06 02:07 | シオ提案「途中ステップにヒント注入」。top1近傍注入→確証バイアス発生(誤答top1を強化)。3ケース中2/3 | hint_injection_demo.py (新規) |
| 2026-04-06 02:10 | シオ提案「対象以外の文脈から注入」。位相距離版は箸バイアス(小コーパスの偶然で常に箸勝利)、1/3 | context_hint_demo.py (新規) |
| 2026-04-06 02:13 | pair統計アライメント版。学習済みco-occurrenceから候補選択、確証バイアス排除して3/3正解 | pair_hint_demo.py (新規) |
| 2026-04-06 02:17 | ヒント戦略4種比較。continuous(毎step弱注入)が11/12で最強、sustained(強持続)が7/12で最悪。System 1的 | hint_strategy_compare.py (新規) |
| 2026-04-06 02:21 | **次単語予測の自然発生**。15passでtop-5=44.7%、30passで48%、重複強調で58.5%/top-10=72%。Transformer/RNNなしで言語モデル化 | next_word_predict.py (新規) |
| 2026-04-06 02:25 | 今夜の総括: 意識最小モデル完成。クオリア→思考ループ→決断エンジン→連想(System1)→メタ認知(System2)→決断→次単語予測 | wave_phase_ablation.md |
| 2026-04-06 17:40 | **ことわざ転移学習実験開始**。シオ提案: 2つの長文に同一ことわざ(弘法にも筆の誤り / 乗りかかった船)を埋め込み、追加学習で予測度が上がるか検証 | kotowaza_transfer_test.py (新規) |
| 2026-04-06 17:52 | wave propagation(Green)が次単語予測に失敗。助詞ハブがグローバル拡散を支配し、ことわざ語が高頻度語に埋もれる。pair統計自体はことわざを正しく捉えてる(弘法→筆=0.84) | kotowaza_transfer_test.py |
| 2026-04-06 17:58 | シオ提案「弘法→想起→弘法に→想起...」自己回帰予測。全語対象だと助詞がクエリ汚染でさらに悪化 | (inline test) |
| 2026-04-06 18:01 | **直接pair参照で逐次予測が成功**。弘法→筆→誤り(学習/未見とも✓)、乗りかかる→船(✓)。chain bigramも弘法→に→も→筆→の 全成功 | (inline test) |
| 2026-04-06 18:02 | **waveは「何を思い出すか」(検索)、pair/chainは「どう組み立てるか」(生成)** — 役割分離を発見 | (設計視点) |
| 2026-04-06 18:09 | シオ提案「音素を1音単位で逐次想起」+ 「グローバル→ローカル切り替え」の2方式 | (設計方針) |
| 2026-04-06 18:13 | ローカルwave成功。助詞除外14ノードサブグラフで弘法→筆rank1、筆→誤りrank2 | (inline test) |
| 2026-04-06 18:14 | **音素prefix × pair統計が圧勝**。音素1つ目(子音)だけで次の語が確定。筆も船も同じ[f]開始だが文脈pairで正しく分岐 | (inline test) |
| 2026-04-06 18:18 | 3方式比較(助詞含む全語逐次予測): 音素式94%(17/18)、ローカル33%、合成83%。音素が圧倒 | (inline test) |
| 2026-04-06 18:22 | 文字形追加は改善なし。外れケース9件は全部pair=0(接続なし)。ゼロに文字形足してもゼロ | (inline test) |
| 2026-04-06 18:25 | chain統計追加で52/60(86.7%)。の→誤り(chain=60)救済。飽和はchain_weight=3 | (inline test) |
| 2026-04-06 18:28 | シオ「バイグラムは人間ぽくない」→ 人間の想起モデルを考察。**予測(流れ)+検証(テンプレート)の二段構造** | (設計視点) |
| 2026-04-06 18:33 | シオ提案「蓄積位相はうろ覚え、検証は想起から仮組立してフェーズマッチ」→ チャンクベース二段予測実装 | (inline test) |
| 2026-04-06 18:37 | 文単位チャンク検証で学習済み文が改善: 弘法17/18→**18/18(100%)**、乗りかかった11/13→12/13 | (inline test) |
| 2026-04-06 18:41 | chain貪欲パスによるチャンク自動抽出が失敗。助詞チェーン(の→だ→ある→と→する→て→いる)が支配的 | (inline test) |
| 2026-04-06 18:43 | シオ提案「累積エネルギーと差分でチャンク境界を検出」→ 位相更新量追跡を実装 | (inline test) |
| 2026-04-06 18:45 | **位相差分で3クラス分離**: 助詞(後半Δ≈0.01,安定), ことわざ語(Δ≈0.01-0.13,中間), 低頻度語(Δ≈0.07-0.23,不安定) | (inline test) |
| 2026-04-06 19:04 | 甘利論文にことわざ埋め込み実験。**pair連結スコアの連続高値区間でチャンク自動検出成功**: 「弘法 に も 筆 の 誤り」が唯一の頻出チャンク | chunk_predict_test.py (新規) |
| 2026-04-06 19:09 | チャンク二段予測: 精度は変わらず(S1で既に正解)。チャンクの役割は予測改善でなく**認識・テンプレート補完・違和感** | chunk_predict_test.py |
| 2026-04-06 19:22 | ChunkTracker動的形成の初回実装(cross/separateモード)。弘法チャンク未検出、要調整。Codexに設計相談→linkスコア+dir_spec+拡張利得の提案を得る | chunk_tracker_test.py (新規), codex_query_chunk_formation.md |
| 2026-04-06 19:31 | シオ提案「チャンクはトークンで持たない。位相差パターンのみ(うろ覚え)」「音と字形のクロスで持つ」 | (設計方針) |
| 2026-04-06 19:39 | 蔵元モデルネットワーク論文(Nögerl & Berloff 2025)を精読。4体結合 sin(θj+θk-θl-θi) で記憶容量が超線形スケール、K/J=1-2がスイートスポット | (論文レビュー) |
| 2026-04-06 19:45 | 4体結合の記憶保持テスト: K_quad=0だとことわざ保持度-0.03(崩壊)、K_quad=0.1で**0.71に跳躍**、0.2で0.78。K/J>3で過剰崩壊 | higher_order_kuramoto_test.py (新規) |
| 2026-04-06 19:49 | 4体結合をことわざ予測に適用: **pair統計が崩壊**(弘法→筆 0.81→0.30→-0.06)。4体項がペアワイズ位相関係を破壊 | jk_kotowaza_test.py (新規) |
| 2026-04-06 19:53 | **quad統計(4体cos)をベースラインで計測**: 弘法にも筆=0.75、にも筆の=0.83。ペアワイズKuramotoだけで4-gram一貫性が自然に生成。4体結合は逆に崩壊させる | jk_quad_stats_test.py (新規) |
| 2026-04-06 19:56 | **結論: 学習側は変えず、計測側にquad_sync追加**。pair連結+quad cosのダブル指標でチャンク検出。論文は「計測の視点」を提供 | (設計方針) |
| 2026-04-06 19:58 | quad統計ベースのチャンク検出+二段予測を実装。pair連結+quad cosダブル指標で「弘法にも筆の誤り」のみ検出(pair=0.84,quad=0.48)。チャンク内は全正解 | quad_chunk_predict.py (新規) |
| 2026-04-06 20:03 | シオ提案「チャンクはあり/なしの2値じゃなく想起度(recall intensity)で」→ quad cosのEMA蓄積で連続的想起度を実装。弘法文で0.18→0.25とgradualに上昇 | recall_intensity_test.py (新規) |
| 2026-04-06 20:05 | 想起度ベース予測で乗り(学習)が14/17→**15/17**に改善。2値チャンクでは拾えなかった「て→継続」が想起度0.27で救済 | recall_intensity_test.py |
| 2026-04-06 20:08 | シオ提案「候補をテンプレートマッチで組み替え」→ 想起度+テンプレート照合（位相差cos一致度）を統合。精度は同等だがボーナスの根拠が統計→位相一致に変化 | recall_intensity_test.py |
| 2026-04-06 20:17 | **デュアル・ウェーブ本体統合**。wave_recallにdual_alpha引数追加(default=0.2)。sqrt(意味関連性)+row(方向性)が独立伝播→観測時α合成。chainが方向情報を提供しrowが非対称化する共犯関係 | reading_session_v2.py |
| 2026-04-06 20:27 | 意識モデル+想起度の統合テスト(hashi判定)。pair_continuous=11/12 vs recall_intensity=10/12。想起度は系列向き、単語判定にはpairが効く | consciousness_recall_test.py (新規) |
| 2026-04-06 20:34 | **モダリティ寄与度分解**（シオ提案）。6モダリティ(phoneme/visual/pair/chain/wave/quad)の個別スコアを可視化。7/8正解、waveとpairが主要根拠 | modality_attribution_test.py (新規) |
| 2026-04-06 20:36 | **拮抗モダリティ除外**（シオ提案）。候補間spread<0.15のモダリティを自動除外して再判定。「木のハシを使う」でphoneme/visual/chain/waveが除外→pair+quadのみ判定（データ偏りで不正解は維持） | modality_attribution_test.py |
| 2026-04-06 20:48 | シオ提案「蓄積→consolidate(睡眠)でチャンク化」。覚醒時はWMで文脈保持、睡眠後に位相パターンだけ残る。Tononiのシナプスhomeostasisと一致 | (設計方針) |
| 2026-04-06 20:55 | WM vs LTテスト: トークン列完全一致ではチャンク0個。前後の文脈が変わるとスパン境界がずれるため | wm_lt_chunk_test.py (新規) |
| 2026-04-06 20:59 | **位相差パターンの文脈非依存性を実証**: 弘法にも筆の誤り、6文で位相差パターンが完全同一(距離=0)。甘利との距離=0.567。分離度∞ | (inline test) |
| 2026-04-06 21:03 | **consolidate v2成功**。相対閾値(距離分布のpercentile)で「弘法にも筆の誤り」「乗りかかった船」がチャンクとして浮上。p5で25チャンク中にことわざ2個 | chunk_consolidate_v2.py (新規) |
| 2026-04-06 21:06 | ことわざ変形テスト: にも→にはで距離0.012、弘法→こうぼうで0.143。筆→ふでは1.37で崩壊（アクセント混入問題） | (inline test) |
| 2026-04-06 21:09 | チャネル別マッチング: 音素チャネルだけで筆=ふで(距離0)、文字一致で誤り=あやまり拾える。「片方一致なら拾う」方式 | (inline test) |
| 2026-04-06 21:13 | **audio_phase_3ch実装**: 音素位相/アクセント位相/combined の3チャネル分離。重み: 音素1.0, アクセント0.3, 文字形0.5。筆=ふでが音素距離0で一致。モジュール設計(将来の生音声入力に差替可能) | reading_session_v2.py |
| 2026-04-06 21:21 | **クロスモーダル想起成功**: 「ふで」聞く→筆(距離0)、「あやまり」→誤り(距離0)が1位で浮かぶ。音素チャネルのチャンクマッチで筆→ふでが0.99→0.00に改善 | (inline test) |
| 2026-04-06 21:26 | シオ提案「助詞の違いは意味の違い。内容語スケルトンでチャンク想起」→ FUNC_WORDSスキップした内容語の音素位相差でマッチング | (inline test) |
| 2026-04-06 21:28 | **内容語スケルトン×音素位相が最強**: にも→でも/には/が 全部距離0で拾える。筆→ふでも距離0。助詞はスケルトンに入らないから影響なし | (inline test) |
| 2026-04-06 21:30 | 残課題: 弘法→こうぼう(g2p読み違い)、誤り→あやまり(lemma変化)はtext→g2pの限界。生音声入力で自動解決する設計 | (既知の制約) |
| 2026-04-06 21:40 | **全文脈保持+累積エネルギー想起**。記憶は消さない、エネルギーで想起しやすさを制御。ことわざエントリE=235-295で蓄積、「ふで,誤り」でクロスモーダル想起成功(match=1.0) | chunk_memory_v3.py (新規) |
| 2026-04-06 21:47 | **連鎖想起(recursive recall)**実装。弘法→pair→筆→skeleton→ことわざ到達。船→pair→乗りかかる(0.96)→到達。筆,誤り→1ステップで弘法チャンクにmatch=1.0 | chunk_memory_v3.py |
| 2026-04-06 21:53 | シオ提案「波動安定度で連鎖想起の深さを動的制御」「想起キャッシュの位相分布で話題判定」 | (設計方針) |
| 2026-04-06 21:56 | シオ提案「想起キャッシュをモダリティ別に」: 相手入力(想起の種)、自己思考(内部)、自己発声(sayと思考が結びつく=自己帰属)、記憶(LT)。3分布の合流点=文脈の焦点 | (設計方針) |
| 2026-04-06 22:00 | **統合プラン策定**。Phase 1-5 + Phase 6(過去成果)の6段階。実験ファイル対応表つき | integration_plan.md (新規) |
| 2026-04-06 22:29 | **Phase 1-A: quad_sync統合完了**。ETA_QUAD=0.05、working_quad_sync/long_term_quad_statsテーブル、学習ループにcos(θa+θb-θc-θd) EMA蓄積、differential decay、consolidate対応。テスト正常(96 quads, ことわざ20回検出) | reading_session_v2.py |
| 2026-04-06 22:35 | 未使用PAIR_POS定数削除。v2では品詞フィルタなし（全lemma対象） | reading_session_v2.py |
| 2026-04-06 22:40 | **Codex指摘2件を修正**: (1)未接触LT quad/pairがworking経由で再加算されるバグ→count=0初期化+count>0のみworking保存 (2)LT total_countを引き継いだcountがconsolidate重みを過大にするバグ→セッション内countのみ使用。pairにも同じバグがあったため両方修正 | reading_session_v2.py |
| 2026-04-06 22:50 | **Phase 2-A/B: ChunkStore+consolidateチャンク検出統合完了**。working_sentences/long_term_chunksテーブル追加。学習時にsent_tokensをworking_sentencesにJSON保存。consolidate_v2末尾で全文再走査→高pair連結span検出→skeleton gap(内容語音素位相差)クラスタリング→long_term_chunks保存。既存類似チャンクはマージ(距離<0.05) | reading_session_v2.py |
| 2026-04-06 22:53 | **Codex指摘3件修正**: (1)chunk_id uuid[:8]衝突→全長uuid (2)_gap_distanceが円周距離未使用→wrap_pi適用 (3)json.loads無防備→try-exceptでスキップ | reading_session_v2.py |
| 2026-04-06 22:57 | **Phase 3: 想起パイプライン統合完了**。6関数追加: _load_recall_state(LT全ロード), phoneme_recall(音素prefix×pair/chain), recall_intensity(quad cos EMA→0-1), recall_next(S1+intensity+template統合), recursive_recall(pair→skeleton→cross-modal連鎖), modality_scores(6モダリティ個別+拮抗判定)。テスト正常 | reading_session_v2.py |
| 2026-04-06 23:06 | **Codex指摘3件修正**: (1)recall_nextの音素フィルタ欠如→target_phoneme_1 optional引数追加 (2)_load_recall_stateがスキーマ未初期化DBでクラッシュ→init_schema_v2()追加 (3)recursive_recallのaudio_phase_3ch多重計算→_ph_cacheでキャッシュ化 | reading_session_v2.py |
| 2026-04-06 23:10 | **Phase 6-A: Green's function統合**。wave_recallをスパースラプラシアンG@u一発に置換。_build_green_dual()でsqrt+row両チャネルのGreen行列を事前計算。Python for loop→scipy sparse matmul | reading_session_v2.py |
| 2026-04-06 23:14 | **Phase 6-B: マチュリティ加重非線形**。wave_recallにmaturity_beta引数追加(default=0)。β>0でiterative fallback(-β·maturity·x³)、β=0でGreen's function(高速)。β=50で高頻度語が深井戸化 | reading_session_v2.py |
| 2026-04-06 23:18 | **Codex指摘3件修正**: (1)β>0分岐の疎行列rs/csリスト混線→sqrt/row別リストに分離 (2)N>5000でN×N密行列OOM→スパースiterative fallback追加 (3)clip/発散ガード欠如→np.clip復活+nan_to_numガード追加 | reading_session_v2.py |
| 2026-04-06 23:32 | **Phase 4設計相談**。Codex+シオ+クオで設計合意。メタデータ(ラベル)は持ち込まない。経路差が自然に位相差として焼き付く方式。aux_phaseの3経路(say/user/recall)。DINO顔ベクトル20次元で99%情報保持。ルートB:顔→記憶の直接想起(名前を経由しない)。顔/物/場所に拡張可能 | codex_query_phase4.md (設計メモ) |
| 2026-04-06 23:53 | **視覚マルチチャネル設計**。シオの洞察: 錐体(RGB 3種)+桿体(明暗)×2目=8ch常時並列。カメラ画像から色相/彩度/明暗/エッジ/パン/チルトの6ch分解。DINO不要、ピクセル演算のみ。処理最適化は人間模倣(中心窩=全ch、周辺視=明暗+動きのみ)。3層パイプライン(分解/空間マップ/想起)。object permanence(パンチルト+背景フローで視界外物体の位置推定) | codex_query_phase4.md (設計メモ) |
| 2026-04-07 16:10 | CLAUDE.md更新: vision-serverの記述をMobileCLIP→DINOv2に修正、パッチベクトル情報追記 | CLAUDE.md |
| 2026-04-07 16:20 | **クロスモーダル蓄積実験**: DINOもOpenCVも使わず位相のみで赤ちゃんモデル。視覚→語、語→視覚の双方向想起が15passで自然発生(9/9正解)。方向トークン追加で視線誘導も創発(4/4正解) | crossmodal_test.py, crossmodal_direction_test.py (新規) |
| 2026-04-07 17:00 | **session-wave-v2 hook実装**: 位相ベースのセッション想起フック。passive-vision独立取得、話者タグ文頭挿入、pair_sync蓄積、wave_recall出力。recall-liteをsession-waveに統合 | session-wave-v2.py, run-session-wave-v2.cmd (新規) |
| 2026-04-07 17:40 | **既存diary焼き直し**: 1077件×8202文をfreshness付きで波動グラフに焼き直し(3.1秒)。テーブル分離(session_sentences/lt_sentences)、avg_freshnessによるエッジ重み | bake_memories.py (新規) |
| 2026-04-07 17:50 | **フレッシュネス伝播減衰検証**: edge_weight×freshnessで古い文の伝播抑制。7クエリ中6つで新しい文が優先(なしだと1/7)。クエリ長による到達深度差も確認(1語→2hit、3語→12hit、古固有3語→22hit) | freshness_decay_test.py, query_length_test.py (新規) |
| 2026-04-07 18:20 | **プールベース想起に全面改修**: Step1(フレッシュネス重み波動→セッションプール)+Step2(LT探索→プール拡張)+Step3(プール内最終wave_recall→top3出力)。唐突度検出、自然減衰 | session-wave-v2.py (改修) |
| 2026-04-07 18:35 | **統一記憶モデル設計確定**: 位相(cos_a,cos_v)は永続・消さない。活性度(avg_freshness)だけ変動。想起でLTP、consolidateで自然減衰(×0.92)、フロア0.01。的確なクエリなら埋没記憶も復活 | (設計決定) |
| 2026-04-07 18:40 | **decay_phase設計**: フレッシュネスを位相化(3チャネル目)。freshness→π×(2f-1)で-π~+πにマップ。zoom-in=+π(新しい記憶)、zoom-out=0(全範囲)。pair_syncにcos_d追加予定 | (設計決定) |
| 2026-04-07 20:40 | **consolidate-wave.py実装**: SessionEndフック。session_sentences→lt_sentences移行、LTD(全ペア×0.92,floor=0.01)、LTP(エネルギー×β=0.005,cap=0.2)。位相は永続、活性だけ変動 | consolidate-wave.py, run-consolidate-wave.cmd (新規) |
| 2026-04-07 20:45 | **エネルギー蓄積実装**: シオ提案「回数ではなくエネルギー」。wave_recall中のエッジ共活性化(\|x[i]·x[j]\|·w)をベクトル化累積。accumulate_energy=Falseデフォルト(Codex指摘: 多重カウント防止) | session-wave-v2.py (改修) |
| 2026-04-07 20:50 | **temporal zoom実装**: Codex推奨A-first hybrid。semantic wave→anchor検出(f<0.9)→adaptive zoom_range→re-seed(同時期lemmas)→Gaussian weight。B案(ペア位相干渉)はavg_freshness集約で橋渡しペアを潰すため不採用 | session-wave-v2.py (改修) |
| 2026-04-07 21:00 | **Codexレビュー5件対応**: (1)エネルギー多重カウント→accumulate_energy制御 (2)LTP_BETA 0.05→0.005 (3)lt_sentencesスコアリング追加 (4)fresh or 1.0バグ修正 (5)race condition→排他的で不要 | session-wave-v2.py, consolidate-wave.py |
| 2026-04-07 21:20 | **エネルギースケール検証**: β=0.005で最大boost=0.031、キャップ到達0%。分解能保持。焦点/プール/劣化/視点が上位=今日の話題が正しく反映 | (検証) |
| 2026-04-07 21:24 | **temporal zoom動作確認**: 蕾クエリで順位変動あり(zoom前: f=0.088の記憶が3位→zoom後: 同時期f=0.010の記憶に入替)。波動クエリでもanchor=0.563周辺に絞り込み成功 | (検証) |
| 2026-04-07 21:27 | lt_sentencesのfreshness DESC LIMIT撤廃。freshnessの減衰自体が自然なフィルタ(シオ指摘) | session-wave-v2.py (改修) |
| 2026-04-07 23:35 | **temporal sketch実験**: ペアに(mean_f, var_f)を持たせるB案。A案(文リランク)との比較で、窓クエリで日付入り記憶が分離、波動クエリでスコア10倍。B案採用決定 | temporal_sketch_test.py (新規) |
| 2026-04-07 23:40 | **temporal sketch統合**: consolidate時にlt_sentences全文スキャン→ペア(mean_f,var_f)計算→DB保存。wave_recall_sparseにtemporal_anchor追加、エッジ重み×exp(-((mean_f-anchor)/spread)^2) | session-wave-v2.py, consolidate-wave.py (改修) |
| 2026-04-07 23:45 | **Codexレビュー6件対応**: (1)save_stateにmean_f/var_f追加(致命バグ修正) (2)staleスケッチNULLクリア (3)migration個別カラムチェック (4-6)既知・低優先 | session-wave-v2.py, consolidate-wave.py |
| 2026-04-07 23:48 | wave-expブランチにコミット(32addf0)。7ファイル+908行 | git commit |
| 2026-04-09 08:40 | **regex fix**: `\F`→`/F` in phase.py。Python 3.12でre.errorになっていた（hookエラーの原因） | wave-phase-core/phase.py |
| 2026-04-09 08:55 | **log-scale temporal sketch**: plasticity正規化(avg=0.15)でsketch mean_fが[0.01,0.1]に潰れていた。log変換で[0.0,0.5]に展開。百人一首anchor=0.5で歌番号復元成功(前はWave/クオに引きずられていた) | constants.py, consolidate-wave.py, session-wave-v2.py |
| 2026-04-09 09:15 | **decay_phase設計検討**: Plan B(語の出現ID位相)とPlan C(pair plasticity位相)を比較。plasticity≠時間(シオ指摘)→IDベースsketchを新設。plasticity sketch=活性度、ID sketch=時系列の二軸 | decay_phase_test.py, id_sketch_test.py (実験) |
| 2026-04-09 09:30 | **dual temporal sketch統合**: session_pairsにmean_id,var_id追加。consolidateで両sketchを同時計算。temporal_mode='plasticity'\|'id'でwave_recall_sparse切替 | consolidate-wave.py, session-wave-v2.py, migrate_wave_db.py |
| 2026-04-09 09:40 | **二層グラフ文波動実験**: 文ノードと語ノードを同一グラフで波動伝播。語ノード経由で文間接続が密になり、シオ散歩→80-100%集中、百人一首→0-40%集中。文のみグラフ(2文ヒット)から劇的改善 | bipartite_wave_test.py (実験) |
| 2026-04-09 09:48 | **bipartite wave recall CLI**: cli.pyを二層グラフに全面書き換え。2パス語グラフ→1パス語+文グラフ。語と文の活性が同一波動方程式から出る | wave-phase-core/cli.py |
| 2026-04-09 09:55 | **未知言語実験(フィンランド語)**: 空白分割のみ、形態素解析なし。60文4トピック×10パスで学習→8クエリ全問正解(100%)。位相の自己組織化だけでトピック想起が動作 | unknown_lang_test.py, unknown_lang_v2_test.py (実験、→share/finnish_experiment.md) |
| 2026-04-09 09:55 | **日本語Unicode分解実験**: 1文字=1トークン。「い-る」cos=0.990で位相ロック、「桜」→「花」(0.036)。ひらがなとカンジがvisual_phaseで自然分離 | unknown_lang_test.py (実験) |
| 2026-04-09 10:05 | wave-expブランチにコミット(f453fbc) | git commit |
| 2026-04-09 10:10 | **未知言語 機能語リストなし実験**: FI_FUNC=空でも8/8正解(100%)。degree saturationが機能語(on,ja等)を自動抑制。人間が与える知識完全にゼロで動作確認 | unknown_lang_v2_test.py (→share/finnish_experiment.md追記) |
| 2026-04-09 10:15 | **日本語Unicode v2 (4トピック)**: 56文×15パス、文字レベル。トピック分類8/10(80%)。桜→花、猫→兎/狐、電車→自転車/駅。空白なし言語で80%は健闘 | jp_unicode_v2_test.py (実験) |
| 2026-04-09 10:20 | **文字+文 二層グラフ想起**: 文字ノード+文ノードのbipartiteで文章復元。醤油砂糖→「醤油と砂糖で煮物を作った」1位、蝶花→「蝶が花から花へ飛んでいる」1位。特徴的クエリで復元成功、1文字クエリは弱い | jp_bipartite_char_test.py (実験) |
| 2026-04-09 10:24 | **語順テスト(文字レベル)**: 正順vs変順で結果完全一致→bag-of-chars状態。pair_syncのsorted keyが語順情報を消している | jp_bipartite_char_test.py (実験) |
| 2026-04-09 10:28 | **逐次波動注入(文字レベル)**: 1文字ずつ波に流して前の揺れに重ねる方式。蜂→花→蜜は正順1位(0.021)、変順ランク外(0.000)。**波の減衰が時間の矢を作る**。4問中2問で語順差が出現 | sequential_wave_test.py (実験) |
| 2026-04-09 10:33 | **非対称逐次注入(音素+字形)**: audio=1音素ずつ(pyopenjtalk g2p)、visual=1文字ずつ。order_biasが日本語語順パターンを捉える（透き通る→て、を→温める、が→流れる）。アクセントH/Lも反映 | asymmetric_wave_test.py (実験) |
| 2026-04-09 10:36 | **逐次クエリ合成**: 学習だけでなくクエリ側も音素逐次注入。Standard(一括)は4問全部同一結果、Sequential(逐次)は2/4問で正順と変順で異なる記憶圏に到達。鳥の例: 正順→溶く/焼く、変順→煮物/砂糖 | asymmetric_wave_test.py (実験) |
| 2026-04-09 21:30 | **逐次注入v2 (56文4トピック)**: 8テストケースでStandard 0/8語順感度、Sequential 4/8語順感度(50%)。鳥の例: 正順0.069で正解1位、変順0.022で正解沈む(3倍差) | sequential_v2_test.py (実験) |
| 2026-04-09 21:38 | **助詞order_bias (甘利論文198文)**: 「する→て」+0.77、「する→た」+0.66が最強。格助詞(が/を/に/の)の前に来る語の位相平均がcos≈1.0で完全一致=名詞クラスタ。「て」前=動詞揃い(cos0.58)、「の」後=名詞揃い(cos0.59)。品詞推定なし | sequential_particle_test.py (実験) |
| 2026-04-09 21:46 | **文間carry-wave**: 波をリセットせず文間で持ち越し(×0.3減衰)。echo pairs(活性残留語×現文語)追加。Reset 5966対 → Carry **8994対**(+3028文間ペア)。「発展-脳」のcos_aが0.69→-0.52に逆転(文脈で位相関係が書き換わる) | cross_sentence_wave_test.py (実験) |
| 2026-04-09 21:59 | **carry-waveテレインセグメンテーション**: 二層グラフ+carry学習でエネルギーテレイン→17セクション分割。前回v1の13セクションより細粒度。論文の流れ(脳進化→AI始まり→LLM→ニューロンモデル→家畜化→兵器→結語)を正確に追跡。学習14.2秒(1文0.014秒) | topic_segment_carry_test.py (実験) |
| 2026-04-09 22:30 | **残響echo実験**: x初期値注入は0/8（クエリに飲まれる）。**リチャージu_totalに加える方式で8/8全問成功**。「学習」がecho文脈(脳/AI/教育/深層/古典)で完全に異なる方向に想起。co-queryと等価だがechoは自然（シオ指摘） | recall_echo_test.py (実験) |
| 2026-04-09 22:55 | **多義語文脈分離**: 「学習」含む文のみ抽出学習→AI文脈(確率,強化)と教育文脈(評価,自信)が完全分離(A∩B∩C=空)。全コーパスでco-query「AI 学習」vs「教育 学習」overlap=0 | topic_carry_test.py (実験) |
| 2026-04-09 23:10 | **残響保持設計確定**: リチャージ方式(u_total=u_query+echo*weight)。トピック切り替わり検出(残響と入力のcos類似度)で蓄積/リセット。飽和防止(エネルギーキャップ)。実装は次回 | (設計決定) |
| 2026-04-10 00:30 | **echo残響保持 実装**: echo_stateテーブル、load/save_echo、リチャージu_total方式。トピック切替検出(cos<0.1→reset)。save_echoはnp.nonzeroで疎イテレーション。L2正規化 | session-wave-v2.py |
| 2026-04-10 00:50 | **CLI echo CoT統合**: wave_recall CLIがecho_stateをDB経由でステップ間持ち越し。broad("弘法")→focus("筆")でecho効果確認 | wave-phase-core/cli.py |
| 2026-04-10 01:00 | **echo関数dedup**: load_echo/save_echo/ECHO定数をwave-phase-core/constants.pyに統合 | constants.py, session-wave-v2.py, cli.py |
| 2026-04-10 01:05 | **文字形逐次テスト**: visual one-shot vs sequential比較。order_biasがone-shot=0.52, sequential=0.27。one-shotのほうが方向性が残る→字形はone-shotが自然 | visual_inject_test.py (実験) |
| 2026-04-10 01:10 | **本番DB逐次焼き直し**: 8356文×1パス、760秒。音素逐次+字形one-shot+carry-wave。弘法→誤り/skeleton、散歩→進捗/連れ出す、桜→開花/予想。旧Kuramoto版より意味的に正確 | rebake_sequential.py |
| 2026-04-10 01:35 | **signed diff不要テスト**: cos-onlyとcos(signed)で5/8一致、3/8微差。想起にはcos_a/cos_vで十分。signedは保険蓄積のみ | (実験) |
| 2026-04-10 01:45 | **視覚モダリティ設計**: イベント駆動(V2E改造)+反対色3ch(赤緑軸/青黄軸/明暗)+ソフトウェア注視+動きベース物体認識。波動逐次注入と同原理 | (設計メモ) |
