// Load the GPU renderer only when the residential map is opened.
window.SentinelResidentialMap = {
  async mount(canvas, options) {
    const {mount} = await import('./map-renderer.js?v=alerts-1');
    return mount(canvas, options);
  },
};
