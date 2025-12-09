using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using DemoApp.Models;
using DemoApp.Data;

namespace DemoApp.Services
{
    public interface IOrderService
    {
        Task<Order> CreateOrderAsync(string userId, List<OrderItem> items);
        Task<Order> GetOrderByIdAsync(int orderId);
        Task<bool> CancelOrderAsync(int orderId);
        Task<List<Order>> GetUserOrdersAsync(string userId);
    }

    public class OrderService : IOrderService
    {
        private readonly IOrderRepository _orderRepository;
        private readonly IInventoryService _inventoryService;
        private readonly IPaymentService _paymentService;
        private readonly ILogger<OrderService> _logger;

        public OrderService(
            IOrderRepository orderRepository,
            IInventoryService inventoryService,
            IPaymentService paymentService,
            ILogger<OrderService> logger)
        {
            _orderRepository = orderRepository;
            _inventoryService = inventoryService;
            _paymentService = paymentService;
            _logger = logger;
        }

        public async Task<Order> CreateOrderAsync(string userId, List<OrderItem> items)
        {
            _logger.LogInformation("Creating order for user: {UserId}", userId);

            // Check inventory
            foreach (var item in items)
            {
                var available = await _inventoryService.CheckAvailabilityAsync(item.ProductId, item.Quantity);
                if (!available)
                {
                    _logger.LogWarning("Insufficient inventory for product: {ProductId}", item.ProductId);
                    throw new InvalidOperationException($"Product {item.ProductId} not available");
                }
            }

            // Calculate total
            decimal total = 0;
            foreach (var item in items)
            {
                total += item.Price * item.Quantity;
            }

            var order = new Order
            {
                UserId = userId,
                Items = items,
                Total = total,
                Status = OrderStatus.Pending,
                CreatedAt = DateTime.UtcNow
            };

            // Save order
            var savedOrder = await _orderRepository.CreateAsync(order);

            // Reserve inventory
            foreach (var item in items)
            {
                await _inventoryService.ReserveAsync(item.ProductId, item.Quantity);
            }

            _logger.LogInformation("Order created successfully: {OrderId}", savedOrder.Id);
            return savedOrder;
        }

        public async Task<Order> GetOrderByIdAsync(int orderId)
        {
            return await _orderRepository.GetByIdAsync(orderId);
        }

        public async Task<bool> CancelOrderAsync(int orderId)
        {
            _logger.LogInformation("Cancelling order: {OrderId}", orderId);

            var order = await _orderRepository.GetByIdAsync(orderId);
            if (order == null)
            {
                return false;
            }

            if (order.Status != OrderStatus.Pending)
            {
                _logger.LogWarning("Cannot cancel order with status: {Status}", order.Status);
                return false;
            }

            // Release inventory
            foreach (var item in order.Items)
            {
                await _inventoryService.ReleaseAsync(item.ProductId, item.Quantity);
            }

            order.Status = OrderStatus.Cancelled;
            await _orderRepository.UpdateAsync(order);

            return true;
        }

        public async Task<List<Order>> GetUserOrdersAsync(string userId)
        {
            return await _orderRepository.GetByUserIdAsync(userId);
        }
    }
}
