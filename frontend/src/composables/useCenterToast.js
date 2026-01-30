import { ref, onBeforeUnmount } from 'vue';

export const useCenterToast = () => {
  const message = ref('');
  let timer = null;

  const show = (text, duration = 2000) => {
    message.value = text;
    if (timer) {
      clearTimeout(timer);
    }
    timer = setTimeout(() => {
      message.value = '';
      timer = null;
    }, duration);
  };

  onBeforeUnmount(() => {
    if (timer) {
      clearTimeout(timer);
      timer = null;
    }
  });

  return { message, show };
};
