using System.Collections.Generic;
using LegacyApi.Repositories;
using LegacyApi.Models;

namespace LegacyApi.Services
{
    public class OrderService
    {
        private readonly OrderRepository _repo;

        public OrderService(OrderRepository repo)
        {
            _repo = repo;
        }

        public IEnumerable<OrderDto> GetActiveOrders()
        {
            return _repo.FindActive();
        }

        public int PlaceOrder(OrderDto dto)
        {
            if (dto.Total <= 0)
            {
                throw new System.ArgumentException("Total must be positive");
            }
            return _repo.Insert(dto);
        }
    }
}
