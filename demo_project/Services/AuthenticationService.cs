using System;
using System.Threading.Tasks;
using Microsoft.Extensions.Logging;
using DemoApp.Models;
using DemoApp.Data;

namespace DemoApp.Services
{
    public interface IAuthenticationService
    {
        Task<AuthResult> LoginAsync(string username, string password);
        Task<bool> ValidateTokenAsync(string token);
        Task LogoutAsync(string userId);
    }

    public class AuthenticationService : IAuthenticationService
    {
        private readonly IUserRepository _userRepository;
        private readonly ITokenService _tokenService;
        private readonly ILogger<AuthenticationService> _logger;

        public AuthenticationService(
            IUserRepository userRepository,
            ITokenService tokenService,
            ILogger<AuthenticationService> logger)
        {
            _userRepository = userRepository;
            _tokenService = tokenService;
            _logger = logger;
        }

        public async Task<AuthResult> LoginAsync(string username, string password)
        {
            _logger.LogInformation("Login attempt for user: {Username}", username);

            var user = await _userRepository.GetByUsernameAsync(username);
            if (user == null)
            {
                _logger.LogWarning("User not found: {Username}", username);
                return AuthResult.Failed("Invalid credentials");
            }

            if (!BCrypt.Net.BCrypt.Verify(password, user.PasswordHash))
            {
                _logger.LogWarning("Invalid password for user: {Username}", username);
                return AuthResult.Failed("Invalid credentials");
            }

            var token = _tokenService.GenerateToken(user);
            _logger.LogInformation("User logged in successfully: {Username}", username);

            return AuthResult.Success(token, user);
        }

        public async Task<bool> ValidateTokenAsync(string token)
        {
            return await _tokenService.ValidateAsync(token);
        }

        public async Task LogoutAsync(string userId)
        {
            _logger.LogInformation("User logging out: {UserId}", userId);
            await _tokenService.RevokeTokenAsync(userId);
        }
    }
}
