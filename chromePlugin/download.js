/**
 * Suno AI 仮想スクロール対応・無限自動ダウンロード
 */
const autoDownloadWithVirtualScroll = async () => { // ← ここから開始
  const sleep = (ms) => new Promise(resolve => setTimeout(resolve, ms));
  const INTERVAL = 1000; 
  const SCROLL_STEP = 222; 

  const dispatchReactClick = (el) => {
    if (!el) return false;
    ['mousedown', 'mouseup', 'click'].forEach(type => {
      el.dispatchEvent(new MouseEvent(type, {
        bubbles: true,
        cancelable: true,
        view: window
      }));
    });
    return true;
  };

  const scroller = document.querySelector('.clip-browser-list-scroller');
  if (!scroller) {
    console.error("スクロールコンテナが見つかりません");
    return; // 関数内なのでこれはOK
  }

  let processedCount = 0;
  let lastScrollTop = -1;

  while (true) {
    // 1. スクロール位置を更新
    scroller.scrollTop = (processedCount / 2) * SCROLL_STEP;
    await sleep(800); // 描画待ちを少し長めに

    // 最下部チェック
    if (scroller.scrollTop === lastScrollTop && processedCount > 0) {
      console.log("最下部に到達したため終了します。");
      break;
    }
    lastScrollTop = scroller.scrollTop;

    // 2. 要素を取得
    // 仮想スクロール対策：[0]番目が常に「今見えている一番上」になります
    const currentRows = document.querySelectorAll('.clip-row');
    const targetRow = currentRows[processedCount]; 

    if (!targetRow) {
      console.log("要素が見つからないため終了します。");
      break;
    }

    console.log(`処理中: ${processedCount}個目付近の要素`);

    // 3. 三点リーダーをクリック
    const moreBtn = targetRow.querySelector('button[aria-label="More options"]');
    if (dispatchReactClick(moreBtn)) {
      await sleep(INTERVAL);

      // 4. 「Download」をクリック
      const downloadBtn = Array.from(document.querySelectorAll('button'))
                               .find(el => el.textContent.includes('Download'));
      if (dispatchReactClick(downloadBtn)) {
        await sleep(INTERVAL);

        // 5. 「MP3 Audio」をクリック
        const mp3Btn = Array.from(document.querySelectorAll('button'))
                            .find(el => el.textContent.includes('MP3 Audio'));
        if (dispatchReactClick(mp3Btn)) {
          console.log(`成功: ${processedCount}番目付近`);
        }
      }
    }

    // カウントアップ（2曲1ペア分）
    processedCount += 2;
    await sleep(INTERVAL);
  }
};

// 実行
autoDownloadWithVirtualScroll();
