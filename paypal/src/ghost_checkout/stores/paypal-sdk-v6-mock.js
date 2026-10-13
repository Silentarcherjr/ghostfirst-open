'use strict';
// OFFLINE MOCK of JS SDK v6 shape. This does not contact or transact with PayPal.
window.paypal = Object.freeze({
  async createInstance() {
    return Object.freeze({
      async findEligibleMethods() { return {isEligible: () => true}; },
      createPayPalOneTimePaymentSession(callbacks) {
        return {async start(options, orderPromise) {
          const order = await orderPromise;
          if (!order.orderId || !order.orderId.startsWith('MOCK-')) throw new Error('mock_order_required');
          // A person must explicitly approve; start() cannot approve for them.
          const dialog = document.createElement('dialog');
          const heading = document.createElement('h2'); heading.textContent = 'SIMULATED PayPal approval';
          const note = document.createElement('p'); note.textContent = 'No money moves. In sandbox, PayPal owns this step.';
          const approve = document.createElement('button'); approve.textContent = 'Approve mock payment';
          const cancel = document.createElement('button'); cancel.textContent = 'Cancel';
          approve.addEventListener('click', async () => {dialog.close();dialog.remove();await callbacks.onApprove({orderId:order.orderId});});
          cancel.addEventListener('click', () => {dialog.close();dialog.remove();callbacks.onCancel?.();});
          dialog.append(heading,note,approve,cancel);document.body.append(dialog);dialog.showModal();
        }};
      }
    });
  }
});
