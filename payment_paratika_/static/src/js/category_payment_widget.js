/**
 * Category-based payment method widget
 */
odoo.define('payment_paratika.category_widget', function (require) {
    'use strict';
    
    const ajax = require('web.ajax');
    
    class CategoryPaymentWidget {
        constructor(options) {
            this.options = options || {};
            this.init();
        }
        
        init() {
            this.bindEvents();
            this.loadCategoryMethods();
        }
        
        bindEvents() {
            // Category change handler for cart preview
            $(document).on('change', '.category-filter-select', (e) => {
                this.loadCategoryMethods($(e.target).val());
            });
        }
        
        async loadCategoryMethods(categoryId) {
            try {
                const result = await ajax.jsonRpc('/payment/paratika/category_methods', 'call', {
                    category_ids: categoryId ? [categoryId] : null
                });
                this.renderMethods(result.payment_methods);
            } catch (error) {
                console.warn('Failed to load payment methods:', error);
            }
        }
        
        renderMethods(methods) {
            const $container = $('#category-payment-methods');
            if (!methods.length) {
                $container.html('<p class="text-muted">Bu kategori için ödeme yöntemi bulunmamaktadır.</p>');
                return;
            }
            
            const html = methods.map(method => `
                <div class="payment-method-card p-2 border rounded mb-2" data-provider="${method.id}">
                    <div class="d-flex align-items-center">
                        ${method.image_128 ? `<img src="data:image/png;base64,${method.image_128}" class="me-2" style="height:32px">` : ''}
                        <strong>${method.name}</strong>
                    </div>
                    ${method.installments?.length ? `
                        <div class="small text-muted mt-1">
                            Taksit: ${method.installments.join(', ')}
                        </div>
                    ` : ''}
                </div>
            `).join('');
            
            $container.html(html);
        }
    }
    
    return CategoryPaymentWidget;
});