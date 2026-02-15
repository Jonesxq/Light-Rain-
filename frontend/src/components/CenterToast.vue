<template>
  <div v-if="message" class="center-toast" role="status" aria-live="polite">
    <div class="toast-card">
      <span class="toast-dot" aria-hidden="true"></span>
      <span class="toast-text">{{ message }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({
  message: {
    type: String,
    default: '',
  },
});
</script>

<style scoped>
.center-toast {
  position: fixed;
  inset: 0;
  display: grid;
  place-items: center;
  pointer-events: none;
  z-index: 9999;
}

.toast-card {
  display: inline-flex;
  align-items: center;
  gap: 10px;
  padding: 14px 20px;
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.86);
  color: #fff;
  font-size: 14px;
  font-weight: 600;
  line-height: 1.4;
  letter-spacing: 0.2px;
  border: 1px solid rgba(255, 255, 255, 0.08);
  box-shadow: 0 20px 50px rgba(15, 23, 42, 0.35);
  backdrop-filter: blur(8px);
  animation: toast-pop 0.25s ease-out;
}

.toast-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: #5eead4;
  box-shadow: 0 0 0 4px rgba(94, 234, 212, 0.2);
}

@keyframes toast-pop {
  from {
    transform: scale(0.96);
    opacity: 0;
  }
  to {
    transform: scale(1);
    opacity: 1;
  }
}
</style>
