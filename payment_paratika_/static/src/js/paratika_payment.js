/**
 * Paratika Payment Frontend Handler for Odoo 19
 * Handles form submission, validation, and API interactions
 */
odoo.define('payment_paratika.paratika_payment', function (require) {
    'use strict';
    
    const payment = require('payment.payment');
    const ajax = require('web.ajax');
    const core = require('web.core');
    const _t = core._t;
    
    const ParatikaPayment = payment.PaymentForm.extend({
        
        events: _.extend({}, payment.PaymentForm.prototype.events, {
            'click .paratika-pay-button': '_onParatikaPayClick',
            'submit form#paratika_payment_form': '_onParatikaFormSubmit',
        }),
        
        /**
         * Initialize Paratika payment handler
         */
        start: function () {
            this._super.apply(this, arguments);
            this._initParatikaHandlers();
            return this._super(...arguments);
        },
        
        /**
         * Initialize event handlers for Paratika-specific elements
         */
        _initParatikaHandlers: function () {
            const self = this;
            
            // Handle installment calculation on change
            this.$el.on('change', 'select[name="installmentCount"]', function () {
                self._calculateInstallment($(this).val());
            });
            
            // Handle bank selection visual feedback
            this.$el.on('click', '.bank-option', function () {
                const $container = $(this).closest('.bank-selector');
                $container.find('.bank-option').removeClass('active border-primary');
                $(this).addClass('active border-primary');
            });
            
            // Card number formatting
            this.$el.on('input', 'input[name="pan"]', function () {
                let value = $(this).val().replace(/\D/g, '');
                value = value.replace(/(.{4})/g, '$1 ').trim();
                $(this).val(value);
            });
            
            // CVV formatting
            this.$el.on('input', 'input[name="cvv"]', function () {
                $(this).val($(this).val().replace(/\D/g, '').slice(0, 4));
            });
        },
        
        /**
         * Handle Paratika pay button click
         */
        _onParatikaPayClick: function (ev) {
            ev.preventDefault();
            
            const $form = $(ev.currentTarget).closest('form');
            const providerId = $form.find('input[name="provider_id"]').val();
            
            // Validate form
            if (!this._validateParatikaForm($form)) {
                return;
            }
            
            // Show loading state
            this._showLoading(true);
            
            // For HPP mode: just submit form
            if ($form.find('input[name="paratika_integration_mode"]').val() === 'hpp') {
                $form.submit();
                return;
            }
            
            // For Direct POST: handle 3D Secure flow
            this._handleDirectPostPayment($form, providerId);
        },
        
        /**
         * Validate Paratika payment form
         */
        _validateParatikaForm: function ($form) {
            const mode = $form.find('input[name="paratika_integration_mode"]').val();
            
            if (mode === 'direct_post' || mode === 'direct_post_moto') {
                // Validate card fields
                const cardNumber = $form.find('input[name="pan"]').val().replace(/\s/g, '');
                const cvv = $form.find('input[name="cvv"]').val();
                const expiryMonth = $form.find('select[name="expiryMonth"]').val();
                const expiryYear = $form.find('select[name="expiryYear"]').val();
                const cardOwner = $form.find('input[name="cardOwner"]').val();
                
                if (!cardNumber || cardNumber.length < 13) {
                    this._showError('Geçerli bir kart numarası giriniz');
                    return false;
                }
                if (!cvv || cvv.length < 3) {
                    this._showError('Geçerli bir CVV kodu giriniz');
                    return false;
                }
                if (!expiryMonth || !expiryYear) {
                    this._showError('Kart son kullanma tarihini seçiniz');
                    return false;
                }
                if (!cardOwner) {
                    this._showError('Kart üzerindeki ismi giriniz');
                    return false;
                }
                
                // Validate bank selection for Direct POST
                if (mode === 'direct_post') {
                    const bank = $form.find('#paratika_bank').val();
                    if (!bank) {
                        this._showError('Lütfen bir banka seçiniz');
                        return false;
                    }
                }
            }
            
            return true;
        },
        
        /**
         * Handle Direct POST payment flow with 3D Secure
         */
        _handleDirectPostPayment: function ($form, providerId) {
            const self = this;
            
            // Serialize form data
            const formData = $form.serializeArray();
            const data = {};
            formData.forEach(field => { data[field.name] = field.value; });
            
            // Add transaction ID
            data.transaction_id = $form.find('input[name="transaction_id"]').val();
            
            // Call backend to process payment
            ajax.jsonRpc('/payment/paratika/process_direct_post', 'call', {
                data: data,
                provider_id: parseInt(providerId),
            }).then(function (result) {
                if (result.status === 'success') {
                    // Redirect to 3D Secure page
                    if (result.redirect_url) {
                        window.location.href = result.redirect_url;
                    } else {
                        // Payment completed
                        window.location.href = result.return_url || '/shop/confirmation';
                    }
                } else if (result.status === '3ds_required') {
                    // Handle 3D Secure challenge
                    self._handle3DSChallenge(result.challenge_data);
                } else {
                    // Error
                    self._showError(result.message || _t('Ödeme işlenemedi'));
                    self._showLoading(false);
                }
            }).catch(function (error) {
                console.error('Direct POST error:', error);
                self._showError(_t('Bağlantı hatası. Lütfen tekrar deneyin.'));
                self._showLoading(false);
            });
        },
        
        /**
         * Handle 3D Secure challenge
         */
        _handle3DSChallenge: function (challengeData) {
            // Create and submit 3DS form
            const $form = $('<form>', {
                method: 'POST',
                action: challengeData.url,
                target: '_self',
            });
            
            Object.keys(challengeData.params).forEach(key => {
                $form.append($('<input>', {
                    type: 'hidden',
                    name: key,
                    value: challengeData.params[key],
                }));
            });
            
            $('body').append($form);
            $form.submit();
        },
        
        /**
         * Calculate installment amounts via AJAX
         */
        _calculateInstallment: function (installmentCount) {
            const self = this;
            const $form = this.$el.find('form');
            
            const amount = parseFloat($form.find('[name="amount"]').val());
            const categoryId = $form.find('[name="category_id"]').val();
            
            if (!amount || !installmentCount) return;
            
            ajax.jsonRpc('/payment/paratika/calculate_installment', 'call', {
                amount: amount,
                installment_count: parseInt(installmentCount),
                category_ids: categoryId ? [parseInt(categoryId)] : null,
            }).then(function (result) {
                if (result.success) {
                    self._updateInstallmentDisplay(result.calculation);
                }
            });
        },
        
        /**
         * Update UI with installment calculation results
         */
        _updateInstallmentDisplay: function (calc) {
            const $container = this.$el.find('.installment-display');
            
            if (!$container.length) {
                this.$el.find('.payment-form').after(
                    $('<div class="installment-display alert alert-info mt-2"></div>')
                );
            }
            
            const html = `
                <div class="d-flex justify-content-between small">
                    <span>Taksit Başına:</span>
                    <strong>${calc.currency} ${calc.per_installment.toFixed(2)}</strong>
                </div>
                ${calc.total_interest > 0 ? `
                <div class="d-flex justify-content-between small text-muted">
                    <span>Toplam Faiz:</span>
                    <span>${calc.currency} ${calc.total_interest.toFixed(2)}</span>
                </div>` : ''}
                <div class="d-flex justify-content-between mt-1">
                    <strong>Toplam Tutar:</strong>
                    <strong>${calc.currency} ${calc.total_amount.toFixed(2)}</strong>
                </div>
            `;
            
            this.$el.find('.installment-display').html(html);
        },
        
        /**
         * Show/hide loading overlay
         */
        _showLoading: function (show) {
            if (show) {
                if (!this.$loadingOverlay) {
                    this.$loadingOverlay = $(`
                        <div class="modal fade show d-block" style="background: rgba(0,0,0,0.5); z-index: 1050;">
                            <div class="modal-dialog modal-sm modal-dialog-centered">
                                <div class="modal-content">
                                    <div class="modal-body text-center py-4">
                                        <div class="spinner-border text-primary" role="status"></div>
                                        <p class="mt-2 mb-0">Ödeme işleniyor...</p>
                                    </div>
                                </div>
                            </div>
                        </div>
                    `);
                    $('body').append(this.$loadingOverlay);
                }
                this.$loadingOverlay.show();
            } else if (this.$loadingOverlay) {
                this.$loadingOverlay.remove();
                this.$loadingOverlay = null;
            }
        },
        
        /**
         * Show error message
         */
        _showError: function (message) {
            // Remove existing alerts
            this.$el.find('.alert-danger').remove();
            
            // Create and insert alert
            const $alert = $(`
                <div class="alert alert-danger alert-dismissible fade show" role="alert">
                    <i class="fa fa-exclamation-circle me-2"></i>${message}
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>
            `);
            
            this.$el.find('.payment-form').first().prepend($alert);
            
            // Auto-dismiss after 5 seconds
            setTimeout(() => {
                $alert.alert('close');
            }, 5000);
        },
    });
    
    // Register the payment form handler
    payment.paymentFormRegistry.add('paratika', ParatikaPayment);
    
    return ParatikaPayment;
});